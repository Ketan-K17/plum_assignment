from pydantic import BaseModel
# from langchain_core.prompts import PromptTemplate
# from llms import chat_llm
# from prompts import CLAIM_CLASSIFY_PROMPT


class ClaimClassification(BaseModel):
    claim_category: str
    confidence: float
    reason: str


# def classify_claim(user_query: str) -> ClaimClassification:
#     prompt = PromptTemplate(
#         template=CLAIM_CLASSIFY_PROMPT,
#         input_variables=["user_query"]
#     )

#     structured_llm = chat_llm.with_structured_output(ClaimClassification)
#     print(chat_llm.llm)

#     chain = prompt | structured_llm

#     result = chain.invoke({"user_query": user_query})
#     return result


# def main():
#     user_query = "I want to submit a consultation claim for fever treatment done on 28 May 2026 at Apollo Hospitals, Bengaluru. Total claim amount is ₹4,500.  Attached documents:  1. dr_arun_sharma_prescription_28_may.jpg 2. apollo_consultation_bill.pdf 3. cbc_and_dengue_report.pdf "

#     classification = classify_claim(user_query)

#     print(f"Claim Category: {classification.claim_category}")
#     print(f"Confidence: {classification.confidence}")
#     print(f"Reason: {classification.reason}")


# if __name__ == "__main__":
#     main()
