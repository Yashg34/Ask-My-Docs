import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class Generator:
    def __init__(self):
        self.model = ChatGoogleGenerativeAI(
            model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
            temperature=0.1,
            max_retries=2
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "You are a strict technical documentation assistant.\n"
             "Answer the user's question relying ONLY on the provided context chunks below.\n"
             "For every claim or factual statement you make, attach the corresponding chunk ID inline like [doc_name:pX:cY].\n"
             "If the supplied context does not contain enough evidence to answer, state clearly that the documentation does not cover this question."),
            ("user", "CONTEXT:\n{context}\n\nQUESTION: {query}\n\nANSWER:")
        ])

        self.chain = self.prompt | self.model | StrOutputParser()

    def generate_answer(self, query: str, context: str) -> str:
        return self.chain.invoke({
            "context": context,
            "query": query
        })