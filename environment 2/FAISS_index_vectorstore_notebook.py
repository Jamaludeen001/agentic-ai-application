# Databricks notebook source
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from delta.tables import DeltaTable
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA

# COMMAND ----------

from pyspark.sql import SparkSession, functions as F, types as T,Window
from delta.tables import DeltaTable

# COMMAND ----------

path="/dbfs/FileStore/tables/faiss_indexes/hnsw_test_index.index"

# COMMAND ----------

model=SentenceTransformer("/dbfs/FileStore/tables/models/bge-small-en-v1.5", local_files_only=True,
        trust_remote_code=True)
D=model.get_sentence_embedding_dimension()

# COMMAND ----------

D

# COMMAND ----------

def empty_and_create_index(D,path):
    #parameter tuning
    N,K=10,2

    def clip(x, min_val, max_val):
        return max(min(x, max_val),min_val)

    x=4*np.ceil(np.log(N))/np.ceil(np.log(10))+8
    M=clip(16,4*np.ceil(np.log(N))/np.ceil(np.log(10))+8,48)
    efConstruction=max(40,8*M)
    efSearch=max(32,2*K,2*M)

    #empty and create new index
    
    base = faiss.IndexHNSWFlat(D, M, faiss.METRIC_INNER_PRODUCT)
    index = faiss.IndexIDMap2(base)

    faiss.write_index(index,path)
    print("created empty index")

# COMMAND ----------

empty_and_create_index(D,path)

# COMMAND ----------

index=faiss.read_index(path)
index

# COMMAND ----------

src_path = "dbfs:/FileStore/tables/delta_embeddings"

# COMMAND ----------

spark

# COMMAND ----------

df=spark.read.format("delta").load(src_path)
display(df.limit(10))

# COMMAND ----------

def add_index(X,id,index):
    xb=np.asarray(X,dtype=np.float32)
    idx=np.asarray(id,dtype=str)

    xb = np.ascontiguousarray(xb.astype("float32"))

    index.add_with_ids(xb,idx)
    return index

# COMMAND ----------

id,X=[],[]
batch_size=5
for r in df.toLocalIterator():
    id.append(r["vector_id"])
    X.append(r["embedding"])
    if len(id)==batch_size:
        index=add_index(X,id,index)
        id,X=[],[]
if id:
    index=add_index(X,id,index)
    id,X=[],[]

   

# COMMAND ----------

index.ntotal

# COMMAND ----------


def plot(X2,sample_size):
    plt.style.use("seaborn-v0_8-whitegrid")  # modern built-in style
    fig, ax = plt.subplots(figsize=(9, 7))
    # Color points by order (often looks like a smooth gradient)
    colors = np.linspace(0, 1, len(X2))

    sc = ax.scatter(
        X2[:, 0], X2[:, 1],
        c=colors,
        cmap="viridis",
        s=14,
        alpha=1,
        edgecolors="white",
        linewidths=80
    )

    ax.set_title(f"FAISS Index Visualization (PCA Projection)\nSample size: {sample_size}", fontsize=14, weight="bold")
    ax.set_xlabel("Principal Component 1 (PC1)", fontsize=12)
    ax.set_ylabel("Principal Component 2 (PC2)", fontsize=12)

    # Add colorbar for visual cue
    cbar = plt.colorbar(sc, ax=ax, pad=0.02)
    cbar.set_label("Point order (for visual gradient)", fontsize=10)

    # Optional: annotate center
    mean_x, mean_y = X2[:, 0].mean(), X2[:, 1].mean()
    ax.scatter(mean_x, mean_y, c="red", s=90, marker="x", linewidths=2, label="Center (mean)")
    ax.legend(frameon=True)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.show()

# COMMAND ----------


def _pca2_numpy(X: np.ndarray) -> np.ndarray:
    
    Xc = X - X.mean(axis=0, keepdims=True)
    # SVD on centered data
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    # Project onto first 2 principal components
    return Xc @ Vt[:2].T

def visualize_faiss_index_pca(index, sample_size=10, seed=42, use_sklearn=True):
    n = index.ntotal
    d = index.d
    if n == 0:
        print("Index is empty.")
        return

    rng = np.random.default_rng(seed)
    m = min(sample_size, n)
    base = index.index if hasattr(index, "index") else index

    # Sample internal positions [0..n-1]
    positions = rng.choice(n, size=m, replace=False)

    X = np.empty((m, d), dtype=np.float32)

    # Reconstruct sampled vectors by INTERNAL position
    for i, pos in enumerate(positions):
        base.reconstruct(int(pos), X[i])

    # PCA -> 2D (sklearn if available; otherwise NumPy fallback)
    if use_sklearn:
        try:
            from sklearn.decomposition import PCA
            X2 = PCA(n_components=2, random_state=seed).fit_transform(X)
        except Exception as e:
            print(f"[Info] sklearn PCA not available ({e}). Falling back to NumPy PCA.")
            X2 = _pca2_numpy(X)
    else:
        X2 = _pca2_numpy(X)

    plot(X2,sample_size)


# COMMAND ----------

faiss.write_index(index,path)

# COMMAND ----------

