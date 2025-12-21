"""
Gemini 3 Flash 모델 테스트
"""
from google import genai
from google.genai import types

# Configure the client
client = genai.Client()

# 간단한 텍스트 생성 테스트
print("=" * 50)
print("Gemini 3 Flash 모델 테스트")
print("=" * 50)

try:
    response = client.models.generate_content(
        model="gemini-3-flash",
        contents="안녕하세요! 간단히 자기소개 해주세요.",
    )

    print("✅ 성공!")
    print(f"응답: {response.text}")

except Exception as e:
    print(f"❌ 오류 발생: {e}")

# Function calling 테스트
print("\n" + "=" * 50)
print("Function Calling 테스트")
print("=" * 50)

schedule_meeting_function = {
    "name": "schedule_meeting",
    "description": "Schedules a meeting with specified attendees at a given time and date.",
    "parameters": {
        "type": "object",
        "properties": {
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of people attending the meeting.",
            },
            "date": {
                "type": "string",
                "description": "Date of the meeting (e.g., '2024-07-29')",
            },
            "time": {
                "type": "string",
                "description": "Time of the meeting (e.g., '15:00')",
            },
            "topic": {
                "type": "string",
                "description": "The subject or topic of the meeting.",
            },
        },
        "required": ["attendees", "date", "time", "topic"],
    },
}

tools = types.Tool(function_declarations=[schedule_meeting_function])
config = types.GenerateContentConfig(tools=[tools])

try:
    response = client.models.generate_content(
        model="gemini-3-flash",
        contents="Schedule a meeting with Bob and Alice for 03/14/2025 at 10:00 AM about the Q3 planning.",
        config=config,
    )

    if response.candidates[0].content.parts[0].function_call:
        function_call = response.candidates[0].content.parts[0].function_call
        print("✅ Function Call 성공!")
        print(f"Function: {function_call.name}")
        print(f"Arguments: {function_call.args}")
    else:
        print("No function call found.")
        print(response.text)

except Exception as e:
    print(f"❌ 오류 발생: {e}")
