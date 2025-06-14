from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import certifi

# MongoDB 연결 설정
ca = certifi.where()
uri = os.getenv("MONGODB_URI")
client = MongoClient(uri, server_api=ServerApi('1'), tlsCAFile=ca)
db = client["UserDB"]
collection = db["Query"]

# OpenAI 클라이언트 초기화
load_dotenv()
openai_api_key = os.getenv('OPENAI_API_KEY')
openai_client = OpenAI(api_key=openai_api_key)

# JSON 파일을 읽고 MongoDB에 데이터 삽입 또는 업데이트하는 함수
def update_user_data(json_file):
    """
    JSON 파일을 읽어서 MongoDB에 user_id를 기준으로 데이터 삽입 또는 새 필드 추가.
    """
    try:
        # JSON 파일 로드
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 데이터가 객체 형식인지 확인
        if not isinstance(data, dict):
            print("JSON 파일이 객체 형식이 아닙니다.")
            return

        # 수정된 코드: JSON에서 user_id, query, indices 가져오기
        user_id = str(data.get("user_id", ""))
        query = data.get("quarry", "")  # "quarry"는 문자열이므로 바로 사용
        indices = data.get("indices", [])  # indices는 리스트로 가져오기


        if not user_id:
            print("JSON 파일에 user_id가 없습니다.")
            return

        user_data = collection.find_one({"user id": user_id})

        if user_data:
            existing_fields = [key for key in user_data.keys() if key.startswith("query_") or key.startswith("indices_")]
            max_index = max([int(field.split("_")[1]) for field in existing_fields if "_" in field], default=0)
        else:
            max_index = 0

        # 입력으로 들어오는 query와 indices 값들을 업데이트
        new_query_field = f"query_{max_index + 1}"
        new_indices_field = f"indices_{max_index + 1}"

        books = ", ".join(map(str, indices)) if indices else ""  # 비어 있으면 공백

        update_fields = {
            "$set": {
                new_query_field: query,
                new_indices_field: books
            }
        }

        collection.update_one({"user id": user_id}, update_fields, upsert=True)
        print(f"user id '{user_id}' 데이터가 저장되었습니다.")

        # 최근 추가된 데이터 가져오기
        user_data = collection.find_one({"user id": user_id})
        recent_data = {}

        if user_data:
            # query_와 indices_ 필드를 동적으로 가져오기 (최대 3개까지)
            query_fields = sorted(
                [(key, user_data[key]) for key in user_data if key.startswith("query_")],
                key=lambda x: int(x[0].split("_")[1]),
                reverse=True
            )[:3]  # 최대 3개까지만 가져오기

            indices_fields = sorted(
                [(key, user_data[key]) for key in user_data if key.startswith("indices_")],
                key=lambda x: int(x[0].split("_")[1]),
                reverse=True
            )[:3]  # 최대 3개까지만 가져오기

            # 가져온 query와 indices를 recent_data에 추가
            for i, (q, idx) in enumerate(zip(query_fields, indices_fields)):
                recent_data[f"query_{i + 1}"] = q[1]
                recent_data[f"indices_{i + 1}"] = idx[1]

        print("최근 추가된 데이터:", recent_data)
        return recent_data

    except FileNotFoundError:
        print(f"JSON 파일 '{json_file}'을 찾을 수 없습니다.")
    except json.JSONDecodeError:
        print("JSON 파일 형식이 올바르지 않습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")

# 사용자 데이터 모델 정의 (Pydantic을 사용)
class KeywordEmbeddingResponse(BaseModel):
    keywords: list[str]  # keywords는 문자열 목록
    vector: list[float]  # vector는 실수 숫자 목록
    indices: list[str]   # 인덱스 목록

# 키워드 추출 함수
def extract_keywords_from_queries(previous_queries, current_query):
    response = openai_client.chat.completions.create(
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
    
    raw_keywords = response.choices[0].message.content.strip().splitlines()  # type: ignore
    keywords = [phrase.strip() for phrase in raw_keywords if phrase.strip()]
    return keywords

# 벡터 임베딩 함수
def generate_embedding(keywords):
    combined_keywords = ", ".join(keywords)

    embs = openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=[combined_keywords],
        encoding_format="float",
        dimensions=512
    )
    
    embedding = embs.data[0].embedding
    return embedding

def get_keywords_and_embedding(json_file: str = "extra_query.json"):

    # MongoDB에서 최근 쿼리와 인덱스 가져오기
    recent_data = update_user_data(json_file)
    if not recent_data:
        return {"error": "No recent data found for the user."}

    queries = [
        recent_data.get("query_1", ""),
        recent_data.get("query_2", ""),
        recent_data.get("query_3", ""),
    ]
    indices = [
        recent_data.get("indices_1", ""),
        recent_data.get("indices_2", ""),
        recent_data.get("indices_3", ""),
    ]

    current_query = queries[0]
    previous_queries = [q for q in queries[1:] if q]

    # 키워드 추출
    keywords = extract_keywords_from_queries(previous_queries, current_query)
    print(keywords)

    # 임베딩 생성
    embedding = generate_embedding(keywords)
    print(embedding)

    return KeywordEmbeddingResponse(keywords=keywords, vector=embedding, indices=indices)

get_keywords_and_embedding("extra_query.json")
