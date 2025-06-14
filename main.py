from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os

# OpenAI 클라이언트 초기화
load_dotenv()
openai_api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=openai_api_key)

# FastAPI 앱 인스턴스 생성
app = FastAPI()

# 기본 엔드포인트
@app.get("/")
async def read_root():
    return {"message": "FastAPI 서버가 잘 작동하고 있습니다!"}

# 사용자 데이터 모델 정의 (Pydantic을 사용)
class QueryRequest(BaseModel):
    query_1: str
    indices_1: str
    query_2: str
    indices_2: str
    query_3: str
    indices_3: str

class KeywordEmbeddingResponse(BaseModel):
    keywords: list[str]  # keywords는 문자열 목록
    vector: list[float]  # vector는 실수 숫자 목록
    indices: list[str]   # 인덱스 목록


# 키워드 추출 함수
def extract_keywords_from_queries(previous_queries, current_query):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an AI that helps extract meaningful and concise keywords from user input, focusing on specific adjectives, nouns, or descriptive words. "
                    "The goal is to provide a list of individual keywords or phrases that describe the key aspects of the user's input."
                    "Do not include generic terms like '책', '추천', '분위기', '느낌' or any other overly broad or common words. "
                    "Focus on extracting unique, descriptive, and specific adjectives or attributes that reflect the mood, characteristics, or themes of the request."
                )
            },
            {
                "role": "user",
                "content": (
                    f"The user has asked the following questions in the past: {', '.join(previous_queries)}.\n"
                    f"The user is now asking: '{current_query}'.\n"
                    "Please determine if the current query is a completely different question from the previous ones. "
                    "If it is, only extract keywords from the current query. If it is similar to the previous queries, "
                    "combine the previous queries and current query, summarize them, and then extract keywords.\n"
                    "Output the extracted keywords as individual words or short phrases. Please avoid phrases or sentences, and instead output keywords like 'adjectives', 'descriptive words', or 'attributes'."
                    "Do not include words like '책', '추천', '분위기', '느낌' or other general terms, only include more specific descriptive keywords."
                    "Output the extracted keywords only as a comma-separated list. Do not include any other text, explanations, or labels like 'Keywords:'."
                )
            }
        ]
    )
    
    raw_keywords = response.choices[0].message.content.strip().splitlines() # type: ignore
    keywords = [phrase.strip() for phrase in raw_keywords if phrase.strip()]
    return keywords

# 벡터 임베딩 함수
def generate_embedding(keywords):
    combined_keywords = ", ".join(keywords)

    embs = client.embeddings.create(
        model="text-embedding-3-large",
        input=[combined_keywords],
        encoding_format="float",
        dimensions=512
    )
    
    embedding = embs.data[0].embedding
    return embedding

# API 엔드포인트: 키워드와 임베딩 생성
@app.post("/keyword-embedding")
async def get_keywords_and_embedding(request: QueryRequest):
    # 새 요청 형식에 맞는 데이터 처리
    queries = [
        request.query_1,
        request.query_2,
        request.query_3,
    ]
    indices = [
        request.indices_1,
        request.indices_2,
        request.indices_3,
    ]

    # 가장 최근의 쿼리 추출
    current_query = queries[0]
    # 이전 쿼리들 (최대 2개) 추출
    previous_queries = [q for q in queries[1:] if q]

    # 키워드 추출
    keywords = extract_keywords_from_queries(previous_queries, current_query)

    # 임베딩 생성
    embedding = generate_embedding(keywords)

    return KeywordEmbeddingResponse(keywords=keywords, vector=embedding, indices=indices)

# FastAPI 서버 실행 (uvicorn을 통해)
# uvicorn filename:app --reload
