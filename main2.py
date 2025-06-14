from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import json
import certifi
import os

ca = certifi.where()

uri = os.getenv("MONGODB_URI")
client = MongoClient(uri, server_api=ServerApi('1'), tlsCAFile=ca)


db = client["UserDB"] 
collection = db["Query"] 

# 연결 확인
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"Connection failed: {e}")

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

        # JSON에서 user_id, query, indices 가져오기
        user_id = data.get("user_id")
        user_id = str(user_id)  # user_id를 문자열로 변환
        query = data.get("quarry", [""])[0]
        indices = data.get("indices", [])  # 비어 있으면 빈 리스트로 처리

        if not user_id:
            print("JSON 파일에 user_id가 없습니다.")
            return

        user_data = collection.find_one({"user id": user_id})

        if user_data:
            existing_fields = [key for key in user_data.keys() if key.startswith("query_") or key.startswith("indices_")]
            max_index = max([int(field.split("_")[1]) for field in existing_fields if "_" in field], default=0)
        else:
            max_index = 0

        new_query_field = f"query_{max_index + 1}"
        new_indices_field = f"indices_{max_index + 1}"

        books = ", ".join(map(str, indices)) if indices else ""  # 비어 있다면 공백

        update_fields = {
            "$set": {
                new_query_field: query,
                new_indices_field: books
            }
        }

        collection.update_one({"user id": user_id}, update_fields, upsert=True)
        print(f"user id '{user_id}' 데이터가 저장되었습니다.")

        user_data = collection.find_one({"user id": user_id})
        recent_data = {}
        if user_data:
            query_fields = sorted(
                [(key, user_data[key]) for key in user_data if key.startswith("query_")],
                key=lambda x: int(x[0].split("_")[1]),
                reverse=True
            )
            indices_fields = sorted(
                [(key, user_data[key]) for key in user_data if key.startswith("indices_")],
                key=lambda x: int(x[0].split("_")[1]),
                reverse=True
            )

            for i, (q, idx) in enumerate(zip(query_fields[:3], indices_fields[:3])):
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

# JSON 파일 경로 설정 및 함수 호출
json_file_path = "extra_query.json"  # JSON 파일 경로
update_user_data(json_file_path)
