# Databricks notebook source
import sys
from pathlib import PurePosixPath, Path

project_root="/Workspace/Users/jamaludeen.fisudeen@fpl.com/Agentic AI Application"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print("✅ Added to sys.path:", project_root)
print("sys.path[0]:", sys.path[0])

# COMMAND ----------

import fitz  # PyMuPDF
from collections import Counter

def extract_spans(pdf_path: str):
    doc = fitz.open(pdf_path)
    spans = []
    for p in range(len(doc)):
        page = doc[p]
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if text!="":
                        spans.append({
                        "page": p + 1,
                        "text": text,
                        "size": span.get("size", 0),
                        "font": span.get("font", ""),
                        "flags": span.get("flags", 0),
                    })

    return spans


# COMMAND ----------

file_path="/dbfs/FileStore/tables/pdf_files/sample_confluence_pdf.pdf"
spans=extract_spans(file_path)

# COMMAND ----------

spans

# COMMAND ----------

spans[0]

# COMMAND ----------

doc_tree={}
root=0

def check_bold(idx):
    if "bold" in str.lower(spans[idx]["font"]):
        return 1
    return 0

def add_node(doc_tree,root,node_index,node_size):
    if not doc_tree:
        doc_tree[node_index]=[node_size,[]]
        root=node_index
        
    elif node_size < doc_tree[root][0]:
        if doc_tree[root][1]:
            last_child=doc_tree[root][1][-1][0]
            last_child_size=spans[last_child]["size"]
            
        if ((not doc_tree[root][1]) or (node_size>last_child_size) or 
            (node_size==last_child_size and check_bold(node_index)>=check_bold(last_child))):
            
            doc_tree[root][1].append([node_index,0])
            
        else:
            doc_tree[root][1][-1][1]=1
            if last_child not in doc_tree:
                doc_tree[last_child]=[last_child_size,[[node_index,0]]]
            else:
                add_node(doc_tree,last_child,node_index,node_size)

    else:
        doc_tree[root][1].append([node_index,0])

for num,span in enumerate(spans):
    add_node(doc_tree,0,num,span["size"])
        

# COMMAND ----------

doc_tree.keys()

# COMMAND ----------

from tools.tree_plot import plot_doc_tree_nx_plotly

fig = plot_doc_tree_nx_plotly(
    doc_tree,
    spans,
    root_id=0,
    show_labels=True,
    with_arrows=False,                 
    title="Interactive Doc Tree",
    highlight_flag_edges=True,         
    highlight_splittable_nodes=True    
)

# COMMAND ----------


fig.show()
  

# COMMAND ----------

chunks=[]
temp_text=""
temp_path=spans[0]["text"]+"->"
internal_chunks=[]
def walk(doc_tree,root,temp_text,temp_path,internal_flag):
    childrens=doc_tree[root][1]
    for child,flag in childrens:
        if not flag:
            temp_text+=spans[child]["text"]+" "
        else:
            if internal_flag+flag>1:
                print(f"internal path of node {root} : {temp_path}")
                internal_chunks.append(temp_path)
                internal_flag=0
        
            if temp_text:
                chunks.append([temp_path,temp_text,root])
            temp_text=""
            walk(doc_tree,child,temp_text,temp_path=temp_path+spans[child]["text"]+"->",internal_flag=internal_flag+flag)
            
    if temp_text:
        chunks.append([temp_path,temp_text,root])
        
    

# COMMAND ----------

walk(doc_tree,0,temp_text,temp_path,0)

# COMMAND ----------

len(chunks)

# COMMAND ----------

from tools.chunker import chunk_sentences

# COMMAND ----------

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

# ---------- doc_id generators ----------
def doc_id_from_path(pdf_path: str) -> str:
    norm = str(Path(pdf_path).as_posix()).lower()
    return "doc_" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

# ---------- chunk hash ----------
def make_chunk_hash(doc_id: str,page_no:int, chunk_id: int, content: str) -> str:
    payload = f"{doc_id}::{page_no}::{chunk_id}::{content}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

# ---------- main function ----------
def build_chunks(run_id: str, pdf_path: str, page_no: int, chunk_texts: list[str]):
    
    doc_id = doc_id_from_path(pdf_path)
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    rows = []
    for chunk_id, text in enumerate(chunk_texts, start=1):
        rows.append({
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "pdf_path": str(pdf_path),
            "page_no": page_no,
            "content": text,
            "chunk_hash": make_chunk_hash(doc_id, page_no, chunk_id, text),
            "run_id":run_id
        })
        
    return rows

# COMMAND ----------

chunks[0]

# COMMAND ----------

pdf_path = r"/dbfs/FileStore/tables/pdf_files/sample_confluence_pdf.pdf"
run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
content_chunks=[]
page_chunks=[]
old_page=1
for  chunk in chunks:
    section="->".join(chunk[0].split("->")[-3:-1])
    temp_chunks=chunk_sentences([chunk[1]])
    root=chunk[2]
    for idx,temp_chunk in enumerate(temp_chunks):
        temp_chunks[idx]=f"[Section: {section}] "+temp_chunk

    if spans[root]['page']==old_page:
        page_chunks.extend(temp_chunks)
    else:
        content_chunks.extend(build_chunks(run_id,pdf_path, old_page, page_chunks))
        old_page=spans[root]['page']
        page_chunks=temp_chunks[:]

content_chunks.extend(build_chunks(run_id,pdf_path, old_page, page_chunks))

    

# COMMAND ----------

len(chunks)

# COMMAND ----------

# just testing with the content_chunks

# COMMAND ----------

len(content_chunks)

# COMMAND ----------

content_chunks

# COMMAND ----------

import os, json
from datetime import datetime

#===========================storing the chunk into the staging=====================================

base_dir = os.path.join("staging", "chunks")
os.makedirs(base_dir, exist_ok=True)

filepath = os.path.join(base_dir, f"chunks_{run_id}.json")

print("Writing to:", os.path.abspath(filepath))

with open(filepath, "w", encoding="utf-8") as f:
    json.dump(content_chunks, f, ensure_ascii=False, indent=4)

# COMMAND ----------

content_chunks[14]

# COMMAND ----------

check_chunk_hash=[]
for chunk in content_chunks:
    if chunk["chunk_hash"] not in check_chunk_hash:
        check_chunk_hash.append(chunk["chunk_hash"])

# COMMAND ----------

len(check_chunk_hash)

# COMMAND ----------

