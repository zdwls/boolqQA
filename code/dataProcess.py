"""
@Author: Dawei Zhu
@Date: 2020-12-18
@Description: 本模块利用torchtext搭建数据通路
"""

import json
import torchtext
from torchtext import data,vocab
from torchtext.data import Iterator, BucketIterator #后者自动选取样本长度相似的数据来构建批数据。但是在测试集中一般不想改变样本顺序，因此测试集使用Iterator迭代器来构建。
import torch
import os
import torch.nn as nn
from nltk.tokenize import wordpunct_tokenize
import time

import torch.utils.data

from transformers import *
 

# 以下定义两个Field,Text-Field use vocab=true在生成迭代器的时候，将文本自动转化为vocab中的id，而label本身就是int 不需要numericalize，所以use vocab=false
TEXT_Field = torchtext.data.Field(sequential=True, tokenize=wordpunct_tokenize,batch_first=True,lower=True, fix_length=None, init_token="<SOS>", eos_token="<EOS>")
LABEL_Field = torchtext.data.Field(sequential=False, use_vocab=False,batch_first=True)
LENGTH_Field = torchtext.data.Field(sequential = False, use_vocab = False, batch_first = True)


#一个封装好的Dataset类，用于torchtext做相应的field处理
class Mydataset(torchtext.data.Dataset):

    def __init__(self,datafile, with_title,is_test,**kwargs):#with title的方式是naive的拼接
        
        self.examples = []
        fields = [('passage',TEXT_Field),('question',TEXT_Field),('len_passage',LENGTH_Field),('len_question',LENGTH_Field),('label',LABEL_Field)]
        if is_test:
            fields[-1] = ('label',None)#对于test没有对应的label
        
        with open(datafile, "r", encoding='utf-8') as rfd:
            for data_line in rfd:
                data_json = json.loads(data_line)
                passage = data_json['title'] + data_json['passage'] if with_title else data_json['passage']
                question = data_json['question']

                len_passage = len(wordpunct_tokenize(passage)) + 2
                len_question = len(wordpunct_tokenize(question)) + 2#<sos>和<eos>
                label = None if is_test else data_json['answer']
                self.examples.append(torchtext.data.Example.fromlist([passage, question, len_passage, len_question, label], fields))

        super(Mydataset, self).__init__(self.examples, fields, **kwargs)
    
    def __len__(self):
        return len(self.examples)
    
    #用于迭代器读取数据
    def __getitem__(self,index):
        return self.examples[index]




class Mydataset_for_bert(torch.utils.data.Dataset):

    def __init__(self,filename,tokenizer,with_title,is_test):#bert的最大长度为512
        
        self.data_bert = []
        with open(filename, "r", encoding='utf-8') as rfd:
            for data_line in rfd:
                data_json = json.loads(data_line)
                self.data_bert.append(data_json)
        self.tokenizer=tokenizer
        self.with_title = with_title
        self.is_test=is_test
    
    def __len__(self):
        return len(self.data_bert)
    
    
    def __getitem__(self,index):
        data_json = self.data_bert[index]
        psg = data_json['passage']
        qst = data_json['question']
        title = data_json['title']
        label = 0 if self.is_test else data_json['answer']#根据传入是否是test来决定label
        if self.with_title:psg = title + psg#拼接到最前面

        #tokenizer同时做分割和encode到id，这里利用两次sep_token与title分割
        tokens = self.tokenizer(psg,qst, add_special_tokens=True, max_length = 320, padding='max_length',truncation=True,return_attention_mask = True, return_tensors='pt')
        
        input_ids = torch.squeeze(tokens['input_ids'])#要做squeeze,因为tokenizer会默认多一个维度
        attention_mask = torch.squeeze(tokens['attention_mask'])


        return input_ids, attention_mask,int(label)





# 加载验证集和训练集。测试集相关部分有待补充
def construct_dataset():
    train_data,valid_data,test_data = Mydataset('../datafile/train.jsonl',False,False),Mydataset('../datafile/dev.jsonl',False,False),Mydataset('../datafile/test.jsonl',False,True)
    #train_data_bert,valid_data_bert,test_data_bert = Mydataset_for_bert()
    return train_data,valid_data,test_data


if __name__ == "__main__":
    
    GLOVE_PATH = "../datafile/glove.6B.100d.txt" # 全局变量，指向预训练词向量
    device = torch.device("cuda:1" if torch.cuda.is_available() else "cpu")
    s=time.time()
    train_data,valid_data,test_data = construct_dataset()
    if not os.path.exists("../datafile/.vector_cache"):
        os.mkdir("../datafile/.vector_cache")
    TEXT_Field.build_vocab(train_data, vectors=vocab.Vectors(GLOVE_PATH)) #由train_dataset构建映射关系,vocab是属于field的信息
    vocab = TEXT_Field.vocab
    print(len(vocab))
    # 获取训练集和验证集的迭代器，在迭代的时候自动numericalize，这是由Field内嵌完成的，对应的就是field自己的vocab,也就是根据
    train_iter = BucketIterator(
        train_data,
        train = True,
        batch_size = 128,
        device=device,
        sort_within_batch=False,
        sort = False,
        repeat=False
    )

    #valid和test在设施iterator的时候设置为false，则不会shuffle,注意最后一个batch不会舍弃剩余数据
    valid_iter=Iterator(
        valid_data,
        train = False,
        batch_size = 128,
        device=device,
        sort_within_batch=False,
        sort = False,
        repeat=False
    )
    test_iter = Iterator(
        test_data,
        train=False,
        batch_size = 64,
        device = device,
        sort = False,
        repeat = False
    )

    # 简单的sanity check
    for idx, batch in enumerate(test_iter):
        if idx>0:break
        print(batch)
        
        
        ques,passage,len_passage,len_question = batch.question,batch.passage,batch.len_passage,batch.len_question
        
        print("question:",ques)
        print("passage:",passage)
        print("len_passage",len_passage)
        print("len_question",len_question)


        print(" ".join([vocab.itos[num.item()] for num in ques[1]]))
        print(" ".join([vocab.itos[num.item()] for num in passage[1]]))
        print(len_passage[1].item())
        print(len_question[1].item())
        
        

    print('耗时：',(time.time()-s)/60,' min')