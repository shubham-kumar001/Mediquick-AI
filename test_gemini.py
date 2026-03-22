from google import genai

client = genai.Client(api_key="AIzaSyDk2cWagC9L8NggIh3h4oFL-2qBvmquSPI")

try:
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents="Say hello"
    )
    print("✅ API Working:", response.text)
except Exception as e:
    print("❌ API Error:", e)