
from .DocRanker import DocDB
from multiprocessing.util import Finalize
import time
import pandas as pd
import logging
# import prettytable
import numpy as np
import scipy.sparse as sp
from .DocRanker import docranker_utils
from .DocRanker.tokenizer import CoreNLPTokenizer
from multiprocessing.pool import ThreadPool
from functools import partial
import numpy as np
import scipy.sparse as sp
import json


class TfidfDocRanker(object):
    """Loads a pre-weighted inverted index of token/document terms.
    Scores new queries by taking sparse dot products.
    """

    def __init__(self, tfidf_path, strict=False):
        """
        Args:
            tfidf_path: path to saved model file
            strict: fail on empty queries or continue (and return empty result)
        """

        matrix, metadata = docranker_utils.load_sparse_csr(tfidf_path)
        self.doc_mat = matrix
        self.ngrams = metadata['ngram']
        self.hash_size = metadata['hash_size']
        self.tokenizer = CoreNLPTokenizer()
        self.doc_freqs = metadata['doc_freqs'].squeeze()
        self.doc_dict = metadata['doc_dict']
        self.num_docs = len(self.doc_dict[0])
        self.strict = strict

    def get_doc_index(self, doc_id):
        """Convert doc_id --> doc_index"""
        return self.doc_dict[0][doc_id]

    def get_doc_id(self, doc_index):
        """Convert doc_index --> doc_id"""
        return self.doc_dict[1][doc_index]

    def closest_docs(self, query, k=1):
        """Closest docs by dot product between query and documents
        in tfidf weighted word vector space.
        """
        spvec = self.text2spvec(query)
        res = spvec * self.doc_mat

        # print(f"{res.data.shape=}")
        # print(f"{type(res)=}")

        if len(res.data) <= k:
            o_sort = np.argsort(-res.data)
        else:
            o = np.argpartition(-res.data, k)[0:k]
            o_sort = o[np.argsort(-res.data[o])]

        doc_scores = res.data[o_sort]
        doc_ids = [self.get_doc_id(i) for i in res.indices[o_sort]]
        return doc_ids, doc_scores

    def batch_closest_docs(self, queries, k=1, num_workers=None):
        """Process a batch of closest_docs requests multithreaded.
        Note: we can use plain threads here as scipy is outside of the GIL.
        """
        with ThreadPool(num_workers) as threads:
            closest_docs = partial(self.closest_docs, k=k)
            results = threads.map(closest_docs, queries)
        return results

    def parse(self, query):
        """Parse the query into tokens (either ngrams or tokens)."""
        # print(query)
        tokens = self.tokenizer.tokenize(query)
        return tokens.ngrams(n=self.ngrams, uncased=True,
                             filter_fn=docranker_utils.filter_ngram)

    def text2spvec(self, query):
        """Create a sparse tfidf-weighted word vector from query.

        tfidf = log(tf + 1) * log((N - Nt + 0.5) / (Nt + 0.5))
        """
        # Get hashed ngrams
        words = self.parse(docranker_utils.normalize(query))
        wids = [docranker_utils.hash(w, self.hash_size) for w in words]

        if len(wids) == 0:
            if self.strict:
                raise RuntimeError('No valid word in: %s' % query)
            else:
                print('No valid word in: %s' % query)
                return sp.csr_matrix((1, self.hash_size))

        # Count TF
        wids_unique, wids_counts = np.unique(wids, return_counts=True)
        tfs = np.log1p(wids_counts)

        # Count IDF
        Ns = self.doc_freqs[wids_unique]
        idfs = np.log((self.num_docs - Ns + 0.5) / (Ns + 0.5))
        idfs[idfs < 0] = 0

        # TF-IDF
        data = np.multiply(tfs, idfs)

        # One row, sparse csr matrix
        indptr = np.array([0, len(wids_unique)])
        spvec = sp.csr_matrix(
            (data, wids_unique, indptr), shape=(1, self.hash_size)
        )

        return spvec



# Theme-wise
# df_ = pd.read_csv("data-dir/train_data.csv")
# themes = df_['Theme'].unique()
# tsince = int(round(time.time()*1000))
# num_app = 0
# num_T = 0
# for theme in themes:
#     ranker = TfidfDocRanker(
#         tfidf_path=f"data-dir/theme_wise/{theme.casefold()}/sqlite_para-tfidf-ngram=2-hash=16777216-tokenizer=corenlp.npz")
#     questions = pd.read_csv(
#         f"data-dir/theme_wise/{theme.casefold()}/questions_only.csv")
#     for idx, row in questions.iterrows():
#         num_T += 1
#         names, _ = ranker.closest_docs(row['Question'], 3)
#         if str(row['id']) in names:
#             num_app += 1
# ttime_elapsed = int(round(time.time()*1000)) - tsince
# ttime_per_example = ttime_elapsed/num_T
# print(f'test time elapsed {ttime_elapsed} ms')
# print(f'test time elapsed per example {ttime_per_example} ms')
# print(f'Acc = {num_app/num_T}, {num_app}, {num_T}')


class Retriever(object):
    def __init__(self, tfidf_path, questions_df, con_idx_2_title_idx, db_path):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter('%(asctime)s: [ %(message)s ]', '%m/%d/%Y %I:%M:%S %p')
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        logger.addHandler(console)
        logger.info('Initializing ranker...')

        self.ranker = TfidfDocRanker(tfidf_path=tfidf_path)

        # all at once
        self.df_q = questions_df
        self.top_3_contexts = []
        self.con_title_id_dict = con_idx_2_title_idx
        self.con_title_id_dict = {str(key): str(val) for key, val in self.con_title_id_dict.items()}

        self.PROCESS_DB = DocDB(db_path=db_path)
        Finalize(self.PROCESS_DB, self.PROCESS_DB.close, exitpriority=100)

    def retrieve_top_k(self, question, title_id, k=1):
        doc_names, doc_scores = self.ranker.closest_docs(question, 100000)
        # print(f"{self.ranker.doc_mat.shape=}")
        # print(f"{doc_names=}")
        # # print("len(doc_names)", len(doc_names))
        # print("title_id", title_id)
        # print("type(title_id)", type(title_id))
        # print(f"{self.con_title_id_dict['11']=}")
        # print(f"{[self.con_title_id_dict[doc] for doc in doc_names]=}")
        doc_names_filtered = [doc for doc in doc_names if self.con_title_id_dict[doc] == title_id]
        
        # print(doc_names_filtered)

        if (len(doc_names_filtered) > k):
            doc_names_filtered = doc_names_filtered[0:k]

        doc_text_filtered = [self.fetch_text(idx) for idx in doc_names_filtered]

        # print(self.con_title_id_dict)

        return doc_names_filtered, doc_text_filtered

    def predict_all(self, k=3):
        self.top_3_contexts_ids = []
        for idx, row in self.df_q.iterrows():
            doc_names = self.retrieve_top_k(
                row['Question'], title=str(row['title_id']), k=k)
            self.top_3_contexts_ids.append(doc_names)
        
        return self.top_3_contexts_ids

    def fetch_text(self, doc_id):
        return self.PROCESS_DB.get_doc_text(doc_id)

    # def top3_docs_all(self):
    #     for id_list in self.top_3_contexts_ids:
    #         para_list = []
    #         for id in id_list:
    #             para_list.append(fetch_text(id))
    #         self.top_3_contexts.append(para_list)
    #         # break
    #     # print(len(top_3_contexts[0]))
    #     self.df_q['contexts'] = self.top_3_contexts
    #     self.df_q.to_csv("data-dir/top3_contexts.csv")

    # TODO: Fix
    # def batched_all(self):
    #     tsince = int(round(time.time()*1000))
    #     self.ranker.batch_closest_docs(
    #         queries=self.df_q['Question'].tolist(), k=10, num_workers=2)
    #     ttime_elapsed = int(round(time.time()*1000)) - tsince
    #     ttime_per_example = ttime_elapsed/self.df_q.shape[0]
    #     print(f'Batched test time elapsed {ttime_elapsed} ms')
    #     print(
    #         f'Batched test time elapsed per example {ttime_per_example} ms')

# RetrieverFinal().predict_all()
