# Databricks notebook source
import sys
from pathlib import PurePosixPath, Path

project_root="/Workspace/Users/jamaludeen.fisudeen@fpl.com/Agentic AI Application"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print("✅ Added to sys.path:", project_root)
print("sys.path[0]:", sys.path[0])

# COMMAND ----------

from pypdf import PdfReader
import pysbd 
from tools.pdf_cleaner import clean_pdf_text_preserve_structure
from tools.chunker import chunk_sentences

# COMMAND ----------

file_path="/dbfs/FileStore/tables/pdf_files/sample_confluence_pdf.pdf"
pages=[]
with open(file_path,"rb") as pdf_file:
    reader=PdfReader(pdf_file)
    for page_no,page in enumerate(reader.pages):
        content=page.extract_text()
        pages.append({"page":page_no+1, "content":content})

# COMMAND ----------

pages

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

chunks=[]
run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
pdf_path = r"/dbfs/FileStore/tables/pdf_files/sample_confluence_pdf.pdf"
segmenter = pysbd.Segmenter(language="en", clean=True)
for page in pages:
    cleaned_page=clean_pdf_text_preserve_structure(page["content"])
    page_sentences=segmenter.segment(cleaned_page)
    page_chunks=chunk_sentences(page_sentences)
    chunks.extend(build_chunks(run_id,pdf_path, page["page"], page_chunks))

# COMMAND ----------

len(chunks)

# COMMAND ----------

chunks[0]

# COMMAND ----------

import os, json
from datetime import datetime

#===========================storing the chunk into the staging=====================================

base_dir = os.path.join("staging", "chunks")
os.makedirs(base_dir, exist_ok=True)

filepath = os.path.join(base_dir, f"chunks_{run_id}.json")

print("Writing to:", os.path.abspath(filepath))

with open(filepath, "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=4)

# COMMAND ----------

len(chunks)

# COMMAND ----------



# COMMAND ----------

