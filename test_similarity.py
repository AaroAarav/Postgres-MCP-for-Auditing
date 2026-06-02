import ollama
import math

def cos_sim(v1, v2):
    return sum(a*b for a,b in zip(v1, v2)) / (math.sqrt(sum(a*a for a in v1)) * math.sqrt(sum(b*b for b in v2)))

p1 = "Calculate the total duration_ms for each db_user in the audit log."
p2 = "Get the sum of duration_ms grouped by db_user."
p3 = "What distinct tool names have been logged in the mcp_audit_log table?"
p4 = "What are the distinct tools used in the audit log?"

emb1 = ollama.embeddings(model="nomic-embed-text", prompt=p1)["embedding"]
emb2 = ollama.embeddings(model="nomic-embed-text", prompt=p2)["embedding"]
emb3 = ollama.embeddings(model="nomic-embed-text", prompt=p3)["embedding"]
emb4 = ollama.embeddings(model="nomic-embed-text", prompt=p4)["embedding"]

print(f"Similarity 1-2 (Duration): {cos_sim(emb1, emb2)}")
print(f"Similarity 3-4 (Tools): {cos_sim(emb3, emb4)}")
