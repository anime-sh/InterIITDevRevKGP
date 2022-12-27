import numpy as np
import pandas as pd

import torch
from torch.utils.data import Dataset

from data.preprocess import preprocess_fn
from tqdm import tqdm

from torch.utils.data import DataLoader

# TODO: memory optimization
class SQuAD_Dataset(Dataset):
	def __init__(self, config, df, tokenizer, train):
		self.config = config

		self.tokenizer = tokenizer
		self.df = df.reset_index(drop = True)
		self.train = train


		# preprocess
		self.data = preprocess_fn(self.df, self.tokenizer)
		self.theme_para_id_mapping = self._get_theme_para_id_mapping()

		# TODO: parallelize in batches

		data_keys = ["answers", "context", "id", "question", "title"]

		tokenized_keys = ["question_context_input_ids", "question_context_attention_mask", "question_context_token_type_ids", 
						"title_input_ids", "title_attention_mask", "title_token_type_ids", 
						"context_input_ids", "context_attention_mask", "context_token_type_ids",
						"question_input_ids", "question_attention_mask", "question_token_type_ids",
						"start_positions", "end_positions", "answerable"
						]

		for key in tokenized_keys:
			self.data[key] = []

		# TODO: Parallelise in batches
		for idx in tqdm(range(0, len(self.data["question"]), 32)):
			example = {key: self.data[key][idx:idx+32] for key in data_keys}

			if self.train:
				tokenized_inputs = self._tokenize_train(example)
			else:
				tokenized_inputs = self._tokenize_test(example)


			for key in tokenized_keys:
				self.data[key].extend(tokenized_inputs[key])

		self.id_data_map = self._get_id_data_mapping()

	# Dataset
	# Copy of dataset
	# para ids ==== dataset.data update
	# temporary dataloader ---- 


	def _get_theme_para_id_mapping(self):
		
		# self.data[key][i] == self.df[column name][i]
		map = {}
		title_list = list(set(self.data["title"]))
		map = {title: [i for i in range(len(self.data["title"])) if title == self.data["title"][i]] for title in title_list}
		
		return map
		# for title in title_list:


		# self.data_dict["title"] = [list of all the titles] == "title"

		# map = {}
		# for id in range(len(self.df)):
		# 	title = self.df["Theme"][id]
		# 	if title not in map.keys():
		# 		map[title] = [id]
		# 	else:
		# 		map[title].append(id)

		# return map

	def _get_id_data_mapping(self):

		map = {id: {"start_positions": None,
					"end_positions": None,
					"answerable": None,
					"question_context_input_ids": None,
					"question_context_attention_mask": None,
					"question_context_token_type_ids": None,
					"title_input_ids": None,
					"title_attention_mask": None,
					"title_token_type_ids": None,
					"context_input_ids": None,
					"context_attention_mask": None,
					"context_token_type_ids": None,
					"question_input_ids": None,
					"question_attention_mask": None,
					"question_token_type_ids": None,
					"answers": None,
					"context": None,
					"question": None,
					"title": None,
					} for id in range(self.__len__())}
		
		for id in tqdm(map):
		
			map[id]["start_positions"] = self.data["start_positions"][id]
			map[id]["end_positions"] = self.data["end_positions"][id]
			map[id]["answerable"] = self.data["answerable"][id]

			map[id]["question_context_input_ids"] = self.data["question_context_input_ids"][id]
			map[id]["question_context_attention_mask"] = self.data["question_context_attention_mask"][id]
			map[id]["question_context_token_type_ids"] = self.data["question_context_token_type_ids"][id]
			
			map[id]["title_input_ids"] = self.data["title_input_ids"][id]
			map[id]["title_attention_mask"] = self.data["title_attention_mask"][id]
			map[id]["title_token_type_ids"] = self.data["title_token_type_ids"][id]

			map[id]["context_input_ids"] = self.data["context_input_ids"][id]
			map[id]["context_attention_mask"] = self.data["context_attention_mask"][id]
			map[id]["context_token_type_ids"] = self.data["context_token_type_ids"][id]

			map[id]["question_input_ids"] = self.data["question_input_ids"][id]
			map[id]["question_attention_mask"] = self.data["question_attention_mask"][id]
			map[id]["question_token_type_ids"] = self.data["question_token_type_ids"][id]

			map[id]["answers"] = self.data["answers"][id]
			map[id]["context"] = self.data["context"][id]
			map[id]["question"] = self.data["question"][id]
			map[id]["title"] = self.data["title"][id]
			
		return map

	def _tokenize_train(self, examples):
		# Some of the questions have lots of whitespace on the left, which is not useful and will make the
		# truncation of the context fail (the tokenized question will take a lots of space). So we remove that
		# left whitespace
		examples["question"] = [q.lstrip() for q in examples["question"]]

		# Tokenize our examples with truncation and padding, but keep the overflows using a stride. This results
		# in one example possible giving several features when a context is long, each of those features having a
		# context that overlaps a bit the context of the previous feature.
		inputs = tokenizer(
			examples["question" if pad_on_right else "context"],
			examples["context" if pad_on_right else "question"],
			truncation="only_second" if pad_on_right else "only_first",
			max_length=max_length,
			stride=doc_stride,
			return_overflowing_tokens=True,
			return_offsets_mapping=True,
			padding="max_length",
			return_tensors="pt",
			return_token_type_ids=True
		)

		# Since one example might give us several features if it has a long context, we need a map from a feature to
		# its corresponding example. This key gives us just that.
		sample_mapping = inputs.pop("overflow_to_sample_mapping")
		# The offset mappings will give us a map from token to character position in the original context. This will
		# help us compute the start_positions and end_positions.
		offset_mapping = inputs.pop("offset_mapping")

		# Let's label those examples!
		inputs["start_positions"] = []
		inputs["end_positions"] = []

		for i, offsets in enumerate(offset_mapping):
			# We will label impossible answers with the index of the CLS token.
			input_ids = inputs["input_ids"][i]
			cls_index = input_ids.index(tokenizer.cls_token_id)

			# Grab the sequence corresponding to that example (to know what is the context and what is the question).
			sequence_ids = inputs.sequence_ids(i)

			# One example can give several spans, this is the index of the example containing this span of text.
			sample_index = sample_mapping[i]
			answers = examples["answers"][sample_index]
			# If no answers are given, set the cls_index as answer.
			if len(answers["answer_start"]) == 0:
				inputs["start_positions"].append(cls_index)
				inputs["end_positions"].append(cls_index)
			else:
				# Start/end character index of the answer in the text.
				start_char = answers["answer_start"][0]
				end_char = start_char + len(answers["text"][0])

				# Start token index of the current span in the text.
				token_start_index = 0
				while sequence_ids[token_start_index] != (1 if pad_on_right else 0):
					token_start_index += 1

				# End token index of the current span in the text.
				token_end_index = len(input_ids) - 1
				while sequence_ids[token_end_index] != (1 if pad_on_right else 0):
					token_end_index -= 1

				# Detect if the answer is out of the span (in which case this feature is labeled with the CLS index).
				if not (offsets[token_start_index][0] <= start_char and offsets[token_end_index][1] >= end_char):
					inputs["start_positions"].append(cls_index)
					inputs["end_positions"].append(cls_index)
				else:
					# Otherwise move the token_start_index and token_end_index to the two ends of the answer.
					# Note: we could go after the last offset if the answer is the last word (edge case).
					while token_start_index < len(offsets) and offsets[token_start_index][0] <= start_char:
						token_start_index += 1
					inputs["start_positions"].append(token_start_index - 1)
					while offsets[token_end_index][1] >= end_char:
						token_end_index -= 1
					inputs["end_positions"].append(token_end_index + 1)

		inputs["start_positions"] = torch.tensor(inputs["start_positions"])
		inputs["end_positions"] = torch.tensor(inputs["end_positions"])
		inputs["answerable"] = torch.tensor(inputs["answerable"])

		inputs["question_context_input_ids"] = inputs.pop("input_ids")
		inputs["question_context_attention_mask"] = inputs.pop("attention_mask")
		inputs["question_context_token_type_ids"] = inputs.pop("token_type_ids")

		title_tokenized = self.tokenizer(examples["title"], max_length=512, truncation="longest_first", return_offsets_mapping=True, padding="max_length", return_tensors="pt", return_token_type_ids=True)
		inputs["title_input_ids"] = title_tokenized["input_ids"]
		inputs["title_attention_mask"] = title_tokenized["attention_mask"]
		inputs["title_token_type_ids"] = title_tokenized["token_type_ids"]

		context_tokenized = self.tokenizer(examples["context"], max_length=512, truncation="longest_first", return_offsets_mapping=True, padding="max_length", return_tensors="pt", return_token_type_ids=True)    
		inputs["context_input_ids"] = context_tokenized["input_ids"]
		inputs["context_attention_mask"] = context_tokenized["attention_mask"]
		inputs["context_token_type_ids"] = context_tokenized["token_type_ids"]

		question_tokenized = self.tokenizer(examples["question"], max_length=512, truncation="longest_first", return_offsets_mapping=True, padding="max_length", return_tensors="pt", return_token_type_ids=True)    
		inputs["question_input_ids"] = question_tokenized["input_ids"]
		inputs["question_attention_mask"] = question_tokenized["attention_mask"]
		inputs["question_token_type_ids"] = question_tokenized["token_type_ids"]

		return inputs

	"""
	TODO:
		Write functions for
			1.	Create an updated data dictionary where each ID contains data corresponding to a data point
			2. 	To retrieve para ids for a particular theme 
					May be create a list of paragraphs corresponding to each theme, if we get a theme, just call that list. (efficient)
					Create this in the init method and store as soon as we get the dataframe 
	"""

	def __len__(self):
		return len(self.data["question"])

	def __getitem__(self, idx):
		return {key: self.data[key][idx] for key in self.data.keys()}

	def collate_fn(self, items):

		# batch = {key: torch.stack([x[key] for x in items], dim = 0).squeeze() for key in self.items.keys()}
		# return batch

		batch = {
			"title_input_ids":                      torch.stack([x["title_input_ids"] for x in items], dim=0).squeeze(),
			"title_attention_mask":                 torch.stack([x["title_attention_mask"] for x in items], dim=0).squeeze(),
			"title_token_type_ids":                 torch.stack([x["title_token_type_ids"] for x in items], dim=0).squeeze(),
			
			"context_input_ids":                    torch.stack([x["context_input_ids"] for x in items], dim=0).squeeze(),
			"context_attention_mask":               torch.stack([x["context_attention_mask"] for x in items], dim=0).squeeze(),
			"context_token_type_ids":               torch.stack([x["context_token_type_ids"] for x in items], dim=0).squeeze(),

			"question_input_ids":                   torch.stack([x["question_input_ids"] for x in items], dim=0).squeeze(),
			"question_attention_mask":              torch.stack([x["question_attention_mask"] for x in items], dim=0).squeeze(),
			"question_token_type_ids":              torch.stack([x["question_token_type_ids"] for x in items], dim=0).squeeze(),

	        # TODO: eliminate this here, use torch to concatenate q and p in model forward function
			"question_context_input_ids":           torch.stack([x["question_context_input_ids"] for x in items], dim=0).squeeze(),
			"question_context_attention_mask":      torch.stack([x["question_context_attention_mask"] for x in items], dim=0).squeeze(),
			"question_context_token_type_ids":      torch.stack([x["question_context_token_type_ids"] for x in items], dim=0).squeeze(),

			"answerable":                           torch.stack([x["answerable"] for x in items], dim=0),
			"start_positions":                      torch.stack([x["start_positions"] for x in items], dim=0),
			"end_positions":                        torch.stack([x["end_positions"] for x in items], dim=0),
			
			"title":								[x["title"] for x in items],
			"question":								[x["question"] for x in items],
			"context":								[x["context"] for x in items],
			"id":									[x["id"] for x in items],
		}

		return batch