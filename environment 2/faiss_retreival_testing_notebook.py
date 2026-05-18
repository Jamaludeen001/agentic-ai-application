# Databricks notebook source
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# COMMAND ----------

index_path="/dbfs/FileStore/tables/faiss_indexes/hnsw_test_index.index"
embedding_model_path="/dbfs/FileStore/tables/models/bge-small-en-v1.5"
metadata_path="dbfs:/FileStore/tables/vector_store/metadata_parquet"


# COMMAND ----------

model=SentenceTransformer(embedding_model_path,local_files_only=True,trust_remote_code=True)

# COMMAND ----------

index=faiss.read_index(index_path)

# COMMAND ----------


metadata=spark.read.parquet(metadata_path)

# COMMAND ----------

def get_context(query):
    query_embed=model.encode(query,normalize_embeddings=True)
    qb=query_embed.reshape(1,-1)
    D,ids=index.search(qb,2)
    ids=ids.astype(str)
    filtered_metadata=metadata.filter(metadata.vector_id.isin(*ids[0]))
    f=filtered_metadata.select("content").collect()
    return f



# COMMAND ----------

query="what are the columns ingested ?"
f=get_context(query)
f[0]

# COMMAND ----------

query="how the sensitive informations are to be handled?"
f=get_context(query)
f[0]

# COMMAND ----------

f

# COMMAND ----------

#thus it shows that the contexts has good informations related to the query.

# COMMAND ----------

# thus structure aware chunk and retreival has better performance

# COMMAND ----------

