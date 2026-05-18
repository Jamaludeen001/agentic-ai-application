# Databricks notebook source
# DBTITLE 1,Untitled
from pyspark.sql import SparkSession, functions as F, types as T,Window
from delta.tables import DeltaTable

# COMMAND ----------

output_SCHEMA = T.StructType([
    T.StructField("vector_id", T.StringType(), True),
    T.StructField("embedding", T.ArrayType(T.FloatType()), True),
    T.StructField("model_name", T.StringType(), True),
])

# COMMAND ----------

dbutils.fs.ls("dbfs:/FileStore/tables/vector_store/metadata_parquet")

# COMMAND ----------

path="dbfs:/FileStore/tables/vector_store/metadata_parquet"
metadata_df=spark.read.parquet(path)

# COMMAND ----------

display(metadata_df.limit(10))

# COMMAND ----------

metadata_df.createOrReplaceTempView("metadata")

# COMMAND ----------

result=spark.sql(""" 
SELECT vector_id, content
FROM (
  SELECT
    vector_id,
    content,
    ROW_NUMBER() OVER (
      PARTITION BY vector_id
      ORDER BY created_at DESC
    ) AS rn
  FROM metadata
) t
WHERE rn = 1;""")

# COMMAND ----------

result.count()

# COMMAND ----------

display(result.limit(10))

# COMMAND ----------

_model = None

output_SCHEMA = T.StructType([
    T.StructField("vector_id", T.StringType(), True),
    T.StructField("embedding", T.ArrayType(T.FloatType()), True),
    T.StructField("model_name", T.StringType(), True),
])

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer 
        _model = SentenceTransformer("/dbfs/FileStore/tables/models/bge-small-en-v1.5", local_files_only=True,
        trust_remote_code=True)
    return _model

def embed_partition(pandas_iter):
    model = get_model()  
    model_name=model._first_module().auto_model.config._name_or_path
    for batch_df in pandas_iter:
        texts = batch_df["content"].fillna("").tolist()
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=64)
        batch_df["embedding"] = [v.astype("float32").tolist() for v in vecs]
        batch_df["model_name"] = model_name
        batch_df=batch_df[["vector_id","embedding","model_name"]]
        yield batch_df  
                                                                                                                  

# COMMAND ----------

embedded_df=result.mapInPandas(embed_partition,schema=output_SCHEMA)

# COMMAND ----------

embedded_df=embedded_df.withColumn("created_at",F.current_timestamp())   
embedded_df=embedded_df.select(["vector_id","embedding","model_name","created_at"])
print("completed creating embeddings")

# COMMAND ----------

target_path = "dbfs:/FileStore/tables/delta_embeddings"
target_embeddings=DeltaTable.forPath(spark,target_path)

# COMMAND ----------

(target_embeddings.alias("trgt")
 .merge(embedded_df.alias("src"), "trgt.vector_id = src.vector_id")
 .whenMatchedUpdateAll()
 .whenNotMatchedInsertAll()
 .execute()
)

# COMMAND ----------

final_trgt=spark.read.format("delta").load(target_path)
print(final_trgt.count())

# COMMAND ----------

display(final_trgt)

# COMMAND ----------

# final_trgt = spark.read.format("delta").load(target_path)
# empty_df = final_trgt.limit(0)
# empty_df.write.format("delta").mode("overwrite").save(target_path)

# COMMAND ----------

target_path

# COMMAND ----------

