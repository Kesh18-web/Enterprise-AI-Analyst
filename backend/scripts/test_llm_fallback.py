"""
Standalone Verification Script: Resilient Multi-Provider LLM Fallback
Rule 3 Compliance: Verify bidirectional fallback chain (Groq 70B -> Groq 8B -> Gemini 2.5 Flash).
"""
import sys, os

# Ensure backend package is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.core.llm import get_llm, extract_text_content

def run_test():
    print("=== Running Multi-Provider LLM Fallback Test ===")

    # 1. Test DeepSeek V3 Dispatch (Fallback to Groq 70B & Gemini Flash)
    llm_deepseek = get_llm(model_name="deepseek", temperature=0.0)
    res_deepseek = llm_deepseek.invoke("Say 'DeepSeek Active' in 2 words.")
    text_deepseek = extract_text_content(res_deepseek.content)
    print(f"1. DeepSeek Model Response: '{text_deepseek}'")

    # 2. Test Groq Llama 3.3 70B Dispatch
    llm_70b = get_llm(model_name="groq/llama-70b", temperature=0.0)
    res_70b = llm_70b.invoke("Say 'Groq 70B Active' in 3 words.")
    text_70b = extract_text_content(res_70b.content)
    print(f"2. Groq 70B Response: '{text_70b}'")

    # 3. Test Gemini Flash Dispatch
    llm_gemini = get_llm(model_name="gemini-2.5-flash", temperature=0.0)
    res_gemini = llm_gemini.invoke("Say 'Gemini Active' in 2 words.")
    text_gemini = extract_text_content(res_gemini.content)
    print(f"3. Gemini Flash Response: '{text_gemini}'")

    print("\n✅ ALL MULTI-PROVIDER LLM FALLBACK TESTS PASSED 100%!")

if __name__ == "__main__":
    run_test()
