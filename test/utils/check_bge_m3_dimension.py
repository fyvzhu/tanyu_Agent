"""
检查 BGE-M3 模型维度
"""
from sentence_transformers import SentenceTransformer

print("加载 BGE-M3 模型...")
model = SentenceTransformer('BAAI/bge-m3')

print(f"✅ 模型加载成功")
print(f"   向量维度: {model.get_sentence_embedding_dimension()}")

# 测试生成 embedding
text = "测试文本"
embedding = model.encode(text, normalize_embeddings=True)
print(f"   测试向量维度: {embedding.shape}")
print(f"   测试向量: {embedding[:5]}...")
