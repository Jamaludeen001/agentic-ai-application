# Databricks notebook source
import pyspark
from delta import configure_spark_with_delta_pip
print("pyspark:", pyspark.__version__)

# COMMAND ----------

import os,sys
from pyspark.sql import SparkSession

# COMMAND ----------

def build_spark(app_name="embeddingStoreBuildLocal"):
    HADOOP_HOME = os.environ["HADOOP_HOME"]          # should now be D:/.../hadoop
    HADOOP_BIN  = f"{HADOOP_HOME}/bin"               # D:/.../hadoop/bin

    extra = f"-Dhadoop.home.dir={HADOOP_HOME} -Djava.library.path={HADOOP_BIN}"

    builder = (
        SparkSession.builder
        .appName("SparkWinPathFix")
        .master("local[1]")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.driver.extraJavaOptions", extra)
        .config("spark.executor.extraJavaOptions", extra)
        .config("spark.pyspark.python", sys.executable)
        .config("spark.pyspark.driver.python", sys.executable)
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    )
    spark=configure_spark_with_delta_pip(builder).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    
    return spark

# COMMAND ----------

spark=build_spark()

# COMMAND ----------

from pyspark.sql import SparkSession
from delta import configure_spark_with_delta_pip

builder = (
    SparkSession.builder
    .appName("embeddingStoreBuildLocal")
    .master("local[1]")
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
)

spark = configure_spark_with_delta_pip(builder).getOrCreate()

# COMMAND ----------

print("JAVA_HOME =", os.environ.get("JAVA_HOME"))

# COMMAND ----------

from pyspark.sql import SparkSession

def build_spark_delta():
    builder = (
        SparkSession.builder
        .appName("SparkDeltaLocal")
        .master("local[1]")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        # IMPORTANT on Windows:
        .config("spark.jars.ivy", "C:/tmp/ivy")
        # Explicit Delta package (match your delta-spark version):
        .config("spark.jars.packages", "io.delta:delta-spark_2.13:4.0.1")
        # Delta SQL integration:
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    )
    return builder.getOrCreate()

# COMMAND ----------

spark=build_spark_delta()

# COMMAND ----------

