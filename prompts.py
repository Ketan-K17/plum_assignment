CLAIM_EXTRACTION_PROMPT = """You are a health insurance claim data extractor.

Extract the following 3 datapoints from the accumulated user input. Return null for any datapoint not clearly present.

1. member_id: The member's policy ID (e.g. EMP001, EMP002, DEP001). Look for patterns like EMP/DEP followed by digits.
2. claim_category: Classify the type of claim into exactly one of:
   CONSULTATION, DIAGNOSTIC, PHARMACY, DENTAL, VISION, ALTERNATIVE_MEDICINE
   - Doctor visit / OPD treatment → CONSULTATION
   - Lab tests, MRI, CT, scans, pathology → DIAGNOSTIC
   - Medicine reimbursement / pharmacy purchase → PHARMACY
   - Tooth, gum, dental procedures → DENTAL
   - Eye treatment, glasses, lenses, cataract → VISION
   - Ayurveda, Homeopathy, Unani, Siddha, Naturopathy → ALTERNATIVE_MEDICINE
3. claimed_amount: The numeric amount being claimed in INR. Extract the number only (no currency symbols).

User Input:
{user_query}

Extract whatever datapoints are clearly present. Set missing fields to null.
Set confidence (0.0-1.0) and reason based on how clearly the claim category could be determined."""


# CLAIM_CLASSIFY_PROMPT = """You are a health insurance claim classifier.

# Your task is to classify the claim into exactly one of these categories:

# * CONSULTATION
# * DIAGNOSTIC
# * PHARMACY
# * DENTAL
# * VISION
# * ALTERNATIVE_MEDICINE

# Use the user query, treatment description, and uploaded document names to determine the most likely category.

# Rules:

# * Doctor visit / OPD treatment → CONSULTATION
# * Lab tests, MRI, CT, scans, pathology → DIAGNOSTIC
# * Medicine reimbursement / pharmacy purchase → PHARMACY
# * Tooth, gum, dental procedures → DENTAL
# * Eye treatment, glasses, lenses, cataract → VISION
# * Ayurveda, Homeopathy, Unani, Siddha, Naturopathy → ALTERNATIVE_MEDICINE

# User Query: {user_query}

# Classify this claim into one of the categories above. Return ONLY valid JSON."""