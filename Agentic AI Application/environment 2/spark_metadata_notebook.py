# Databricks notebook source
from pyspark.sql import SparkSession, functions as F, types as T,Window
import os,sys

# COMMAND ----------

spark

# COMMAND ----------


SCHEMA = T.StructType([
    T.StructField("doc_id", T.StringType(), False),
    T.StructField("chunk_id", T.IntegerType(), False),
    T.StructField("pdf_path", T.StringType(), False),
    T.StructField("page_no", T.IntegerType(), True),
    T.StructField("content", T.StringType(), False),
    T.StructField("chunk_hash", T.StringType(), True),
    T.StructField("run_id", T.StringType(), True),

])



# COMMAND ----------

import json,glob,os

chunks_dir = r"/Workspace/Users/jamaludeen.fisudeen@fpl.com/Agentic AI Application/environment 1/staging/chunks"
json_files = sorted(glob.glob(os.path.join(chunks_dir, "*.json")))
chunks=[]

for filepath in json_files:
    with open(filepath, 'r', encoding='utf-8') as file:
            data = json.load(file)
            chunks.extend(data)

# COMMAND ----------

import os
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql import SparkSession

def ingest_metadata_table(
    spark: SparkSession,
    chunks: list,
    metadata_path: str = "./vector_store/metadata_parquet",
    partition_by: str = "doc_id",
    run_id_formats: tuple = ("yyyyMMdd'T'HHmmss'Z'", "yyyy-MM-dd HH:mm:ss.SSS"),
    keep_run_id_in_target: bool = True,   # recommended
):
    # 1) Incoming Dataframe
    incoming = spark.createDataFrame(chunks, schema=SCHEMA)
    
    print(f"incoming data count : {incoming.count()}")
    #incoming.show()
    # 2) creating timestamp from run id
    
    run_ts = None
    for fmt in run_id_formats:
        ts_try = F.to_timestamp(F.col("run_id"), fmt)
        run_ts = ts_try if run_ts is None else F.coalesce(run_ts, ts_try)
    incoming = incoming.withColumn("run_ts", run_ts)

    # 4) Identify impacted doc_ids from incoming data
    
    impacted = [r["doc_id"] for r in incoming.select("doc_id").distinct().collect()]

    # 5) Read ONLY impacted partitions from existing target table
    
    
    existing = None
    existing_all = (
            spark.read
                .option("mergeSchema", "true")  # helpful if schema evolved
                .parquet(metadata_path)
        )
    print("read existing data")

    # 6) Ensure schemas align & add run_ts to existing table (if run_id exists)
    
    if existing_all is not None:
        existing = existing_all.where(F.col("doc_id").isin(impacted))
        print("123",existing.columns)
        if "run_id" in existing.columns:
            print("there is run id")
            existing_run_ts = None
            for fmt in run_id_formats:
                ts_try = F.to_timestamp(F.col("run_id"), fmt)
                existing_run_ts = ts_try if existing_run_ts is None else existing_run_ts
            existing = existing.withColumn("run_ts", existing_run_ts)
        else:
            existing = existing.withColumn("run_ts", F.lit(None).cast("timestamp"))
            
        existing=existing.select(["doc_id","chunk_id","pdf_path","page_no","content","chunk_hash","run_id","run_ts"])
        combined = existing.unionByName(incoming, allowMissingColumns=True)
    else:
        print("combined")
        combined = incoming
    # 3) removing duplicates from combined data
    print(f"total records after combined : {combined.count()}")
    
    w_hash = Window.partitionBy("chunk_hash").orderBy(
        F.col("run_ts").desc_nulls_last(),
        F.col("run_id").desc_nulls_last()
    )
    combined=combined.withColumn("rn",F.row_number().over(w_hash))
    
    combined = (combined
        .filter(F.col("rn") == 1)
        .drop("rn")
    )
    
    print(f"total data after removing duplicates : {combined.count()}")
    #combined.show()
    
    # 7) Latest-only per (doc_id, page_no, chunk_id)
    
    w_pos = Window.partitionBy("doc_id", "page_no", "chunk_id").orderBy(
        F.col("run_ts").desc_nulls_last(),
        F.col("run_id").desc_nulls_last()
    )
    latest = (combined
        .withColumn("rn", F.row_number().over(w_pos))
        .filter(F.col("rn") == 1)
        .drop("rn")
    )

    print(f"total latest data to be overwrite after removing old version data's : {latest.count()}")
    
    # 8) Add vector_id + created_at
    
    latest = (latest
        .withColumn(
            "vector_id",
            F.xxhash64(
                F.col("doc_id"),
                F.col("page_no"),
                F.col("chunk_id"),
                F.coalesce(F.col("chunk_hash"), F.lit(""))
            ).cast("string")
        )
        .withColumn("created_at", F.current_timestamp())
    )

    # 9) Select curated columns
    
    cols = ["vector_id", "doc_id", "chunk_id", "pdf_path", "page_no", "content", "chunk_hash", "created_at","run_id"]
    to_write = latest.select(*cols)

    # 10) Overwrite only impacted partitions
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    (to_write.write
        .mode("overwrite")
        .partitionBy(partition_by)
        .parquet(metadata_path)
    )

    print(f"metadata written to: {metadata_path}")
    print(f"Impacted docs overwritten: {len(impacted)}")
    return metadata_path

# COMMAND ----------

print("creating spark session")
print("starting to create or ingest data into the table")
path = ingest_metadata_table(
        spark=spark,
        chunks=chunks,
        metadata_path="dbfs:/FileStore/tables/vector_store/metadata_parquet"
    )

print("Metadata table stored at:", path)

    # Verify by reading it back
meta_df = spark.read.parquet(path)

# COMMAND ----------

meta_df=spark.read.parquet(path)
meta_df.count()

# COMMAND ----------

display(meta_df.limit(20))

# COMMAND ----------

# empty_df = meta_df.limit(0)
# empty_df.write.mode("overwrite").parquet(path)

# COMMAND ----------

