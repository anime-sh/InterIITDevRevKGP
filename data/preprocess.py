import pandas as pd
from ast import literal_eval

def preprocess_fn(df, mask_token='<mask>'):
	"""
	No preprocessing in v1
	"""

	data_dict = {}
	data_dict["answers"] = []
	data_dict["context"] = []
	data_dict["question_id"] = []
	data_dict["context_id"] = []
	data_dict["title_id"] = []
	data_dict["question"] = []
	data_dict["title"] = []
	data_dict["fewshot_qa_prompt"] = []
	data_dict["fewshot_qa_answer"] = []

	# question ids 
	ques2idx = {}
	idx2ques = {}

	# df["Answer_start"] = df["Answer_start"].apply(lambda x: literal_eval(x) if isinstance(x, str) else x)
	# df["Answer_text"] = df["Answer_text"].apply(lambda x: literal_eval(x) if isinstance(x, str) else x) 

	for index, row in df.iterrows():
		# if isinstance(row["Answer_start"], str):
		# 	answer_start = literal_eval(row["Answer_start"])
		# else:
		# 	answer_start = row["Answer_start"]
		
		# if isinstance(row["Answer_text"], str):
		# 	answer_text = literal_eval(row["Answer_text"])
		# else: 
		# 	answer_text = row["Answer_text"]

		answer_start = row["answer_start"]
		answer_text = row["answer_text"]
		
		context = row["context"]
		question_id = row["question_id"]
		context_id = row["context_id"]
		title_id = row["title_id"]
		question = row["question"]
		title = row["title"]
		answer = {"answer_start": answer_start, "text": answer_text}

		fewshot_qa_prompt = f"Question: {question} Answer: {mask_token} Context: {context}" # 'source_text'
		fewshot_qa_answer = f"Question: {question} Answer: {answer_text}" # 'target_text'
		
		data_dict["answers"].append(answer)
		data_dict["context"].append(context)
		data_dict["question_id"].append(question_id)
		data_dict["context_id"].append(context_id)
		data_dict["title_id"].append(title_id)
		data_dict["question"].append(question)
		data_dict["title"].append(title)
		data_dict["fewshot_qa_prompt"].append(fewshot_qa_prompt)
		data_dict["fewshot_qa_answer"].append(fewshot_qa_answer)

	return data_dict
