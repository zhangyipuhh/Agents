
from langchain_community.document_loaders import UnstructuredHTMLLoader as HTMLoader

loader = HTMLoader("https://docs.langchain.org.cn/oss/python/integrations/document_loaders/microsoft_word")
docs = loader.load()  # 本地解析，无需网络
if __name__ == "__main__":
    if docs:
        print(docs)
