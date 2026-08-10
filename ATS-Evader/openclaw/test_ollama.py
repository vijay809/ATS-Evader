import urllib.request
import json
import traceback

def test():
    url = "http://127.0.0.1:11434/api/tags"
    print(f"Testing URL: {url}")
    try:
        with urllib.request.urlopen(url, timeout=2.0) as response:
            data = response.read()
            print("Response:", data)
            result = json.loads(data)
            print("models in result:", "models" in result)
    except Exception as e:
        print("Exception occurred:")
        traceback.print_exc()

if __name__ == "__main__":
    test()
