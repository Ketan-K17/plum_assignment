from typing import Optional, List
from pydantic import BaseModel, Field


class ConfidenceField(BaseModel):
    """An extracted field value paired with a confidence score (0.0–1.0).

    Scoring rules:
      ~1.0  — printed text, value clearly readable
      ~0.8  — handwritten text, value clearly readable
      0.2–0.5 — partially legible (print or handwriting)
      0.0   — completely unreadable or field absent
    """
    value: Optional[str] = None
    confidence: float  # 0.0 to 1.0


# ---------------------------------------------------------------------------
# Prescription
# ---------------------------------------------------------------------------

class MedicineItem(BaseModel):
    name: ConfidenceField = Field(
        description="Full medicine name as written, including salt name and brand if present. "
                    "E.g. 'Tab Paracetamol 650mg', 'Cap Amoxicillin 500mg'. "
                    "Preserve exactly as written — do not normalize or expand abbreviations."
    )
    dosage: ConfidenceField = Field(
        description="Dosage frequency in standard Indian prescription notation. "
                    "E.g. '1-1-1' means morning-afternoon-night, '0-0-1' means once at night only. "
                    "May also be written as 'TDS', 'BD', 'OD', 'SOS'. Capture exactly as written."
    )
    duration: ConfidenceField = Field(
        description="Duration for which the medicine is to be taken. "
                    "E.g. '5 days', '2 weeks', '1 month'. "
                    "May be written as 'x 5/7' (5 days) or 'x 2/52' (2 weeks) in shorthand."
    )


class PrescriptionDocument(BaseModel):
    doctor_name: ConfidenceField = Field(
        description="Full name of the prescribing doctor, including title. "
                    "E.g. 'Dr. Arun Sharma'. Usually appears at the top of the letterhead."
    )
    doctor_registration_number: ConfidenceField = Field(
        description="Doctor's medical council registration number. "
                    "Follows state-specific formats: KA/XXXXX/YYYY, MH/XXXXX/YYYY, DL/XXXXX/YYYY, etc. "
                    "For Ayurveda practitioners: AYUR/[STATE]/XXXXX/YYYY. "
                    "May be partially obscured by stamps — extract what is visible."
    )
    doctor_specialization: ConfidenceField = Field(
        description="Doctor's medical qualification and specialization. "
                    "E.g. 'MBBS, MD (Internal Medicine)', 'BDS', 'MS (Orthopaedics)'. "
                    "Usually appears below the doctor's name on the letterhead."
    )
    hospital_clinic_name: ConfidenceField = Field(
        description="Name of the hospital or clinic where the prescription was issued. "
                    "E.g. 'City Medical Centre', 'Apollo Clinic'. "
                    "May appear as part of the printed letterhead."
    )
    hospital_address: ConfidenceField = Field(
        description="Full address of the hospital or clinic, including street, area, city, and PIN if visible. "
                    "E.g. '12 MG Road, Bengaluru – 560001'."
    )
    patient_name: ConfidenceField = Field(
        description="Full name of the patient as written on the prescription. "
                    "Usually appears after 'Patient:' or 'Name:' label."
    )
    patient_age: ConfidenceField = Field(
        description="Patient's age as written. E.g. '39 years', '6 months', '45Y'. "
                    "Capture the unit (years/months) if present."
    )
    patient_gender: ConfidenceField = Field(
        description="Patient's gender. Typically written as 'M'/'F', 'Male'/'Female', or 'Male/Female' checkbox. "
                    "Normalize to 'M' or 'F' in output."
    )
    issue_date: ConfidenceField = Field(
        description="Date the prescription was issued. "
                    "May appear in DD-MM-YYYY, DD/MM/YYYY, or written form (e.g. '01-Nov-2024'). "
                    "Normalize to ISO format YYYY-MM-DD if possible."
    )
    diagnosis: ConfidenceField = Field(
        description="Primary diagnosis or clinical impression as written by the doctor. "
                    "May use medical shorthand: HTN = Hypertension, T2DM = Type 2 Diabetes, "
                    "URI = Upper Respiratory Infection, GERD = Gastroesophageal Reflux Disease. "
                    "Capture exactly as written; include secondary diagnoses if present."
    )
    medicines: List[MedicineItem] = Field(
        description="List of all medicines prescribed. Each entry should capture name, dosage, and duration. "
                    "Medicines are typically listed after 'Rx' or a horizontal rule. "
                    "May be numbered or bulleted. Extract all entries even if partially legible."
    )
    investigations_ordered: ConfidenceField = Field(
        description="List of lab tests or diagnostic investigations ordered by the doctor. "
                    "Typically appears under 'Investigations:', 'Advised:', or 'Please do:'. "
                    "E.g. 'CBC, Dengue NS1', 'HbA1c, Lipid Profile, FBS'. "
                    "Capture as a comma-separated string."
    )
    follow_up: ConfidenceField = Field(
        description="Follow-up instructions given by the doctor. "
                    "E.g. 'After 5 days if no improvement', 'Review after 2 weeks with reports'. "
                    "May be absent — set to null if not present."
    )


class BillLineItem(BaseModel):
    description: ConfidenceField = Field(
        description="Name or description of the service, procedure, or item billed. "
                    "E.g. 'Consultation Fee (OPD)', 'CBC (Complete Blood Count)', 'Room Charges – Day 1'. "
                    "Capture exactly as written, including any procedure codes if present."
    )
    quantity: ConfidenceField = Field(
        description="Number of units billed for this line item. Usually '1' for services. "
                    "May be higher for consumables or multi-day charges."
    )
    rate: ConfidenceField = Field(
        description="Per-unit rate or price for this line item in INR. "
                    "E.g. '1000.00'. May be absent on handwritten bills — set to null if not present."
    )
    amount: ConfidenceField = Field(
        description="Total amount for this line item (quantity × rate) in INR. "
                    "E.g. '1000.00'. This is the most critical field — prioritize extraction even if rate is missing."
    )


class HospitalBillDocument(BaseModel):
    hospital_name: ConfidenceField = Field(
        description="Name of the hospital, clinic, or diagnostic centre issuing the bill. "
                    "Usually appears prominently at the top of the document. "
                    "E.g. 'City Medical Centre', 'Precision Diagnostics Pvt Ltd'."
    )
    hospital_address: ConfidenceField = Field(
        description="Full address of the hospital or clinic including street, area, city, and PIN if visible. "
                    "E.g. '12 MG Road, Bengaluru – 560001'."
    )
    gstin: ConfidenceField = Field(
        description="GST Identification Number of the hospital if present. "
                    "Format: 2-digit state code + 10-digit PAN + 1 digit + Z + 1 digit. "
                    "E.g. '29XXXXX1234X1ZX'. Will be absent for small clinics — set to null if not present."
    )
    bill_number: ConfidenceField = Field(
        description="Unique bill or receipt number assigned by the hospital. "
                    "E.g. 'CMC/2024/08321', 'BILL-001234'. "
                    "Usually labeled 'Bill No:', 'Receipt No:', or 'Invoice No:'."
    )
    issue_date: ConfidenceField = Field(
        description="Date the bill was issued. "
                    "May appear in DD-MM-YYYY, DD/MM/YYYY, or written form. "
                    "Normalize to ISO format YYYY-MM-DD if possible."
    )
    patient_name: ConfidenceField = Field(
        description="Full name of the patient as written on the bill. "
                    "Usually appears under 'Patient Name:' or 'Patient:'."
    )
    patient_age: ConfidenceField = Field(
        description="Patient's age as written on the bill. E.g. '39', '39 years', '39Y'. "
                    "May be combined with gender as 'Age/Gender: 39 / Male'."
    )
    patient_gender: ConfidenceField = Field(
        description="Patient's gender as written on the bill. "
                    "Normalize to 'M' or 'F' in output."
    )
    referring_doctor: ConfidenceField = Field(
        description="Name of the doctor who referred the patient or performed the consultation. "
                    "Usually labeled 'Referring Doctor:', 'Consultant:', or 'Dr:'. "
                    "May be absent — set to null if not present."
    )
    line_items: List[BillLineItem] = Field(
        description="Complete list of itemized charges on the bill. "
                    "Each entry captures the service/item description, quantity, rate, and amount. "
                    "Extract all rows from the bill table, including medicines, procedures, and room charges."
    )
    subtotal: ConfidenceField = Field(
        description="Sum of all line item amounts before tax or discounts, in INR. "
                    "Usually labeled 'Subtotal:' or 'Total before GST:'."
    )
    gst_amount: ConfidenceField = Field(
        description="GST charged on the bill in INR. "
                    "Medical services are typically GST-exempt (0%), but diagnostic and pharmacy items may carry GST. "
                    "Set to '0.00' if explicitly shown as zero; null if not mentioned at all."
    )
    total_amount: ConfidenceField = Field(
        description="Final total amount payable by the patient in INR, after tax and any discounts. "
                    "Usually labeled 'Total Amount:', 'Net Payable:', or 'Grand Total:'. "
                    "This is the most critical field on the bill."
    )
    payment_mode: ConfidenceField = Field(
        description="Mode of payment used. E.g. 'Cash', 'UPI', 'Card', 'Cheque'. "
                    "May appear as a checked checkbox or written text. "
                    "Set to null if not mentioned."
    )


class LabTestResult(BaseModel):
    test_name: ConfidenceField = Field(
        description="Name of the individual test or sub-test. "
                    "E.g. 'Hemoglobin', 'WBC Count', 'Platelet Count', 'Dengue NS1 Antigen'. "
                    "For panel tests (e.g. CBC), extract each sub-test as a separate entry."
    )
    result: ConfidenceField = Field(
        description="The reported result value for this test. "
                    "May be numeric (e.g. '13.2') or qualitative (e.g. 'POSITIVE', 'NEGATIVE', 'REACTIVE'). "
                    "Capture exactly as written including any flags like 'H' (High) or 'L' (Low) if present."
    )
    unit: ConfidenceField = Field(
        description="Unit of measurement for the result. "
                    "E.g. 'g/dL', '/μL', 'mg/dL', 'IU/L'. "
                    "Set to null for qualitative results like POSITIVE/NEGATIVE."
    )
    normal_range: ConfidenceField = Field(
        description="Reference range provided by the lab for this test. "
                    "E.g. '13.0 – 17.0', '4,500 – 11,000', '<0.5'. "
                    "May vary by age and gender — capture exactly as printed. "
                    "Set to null if not provided."
    )


class LabReportDocument(BaseModel):
    lab_name: ConfidenceField = Field(
        description="Name of the diagnostic laboratory or imaging centre. "
                    "E.g. 'Precision Diagnostics Pvt Ltd', 'SRL Diagnostics'. "
                    "Usually appears prominently at the top of the report."
    )
    nabl_accredited: ConfidenceField = Field(
        description="Whether the lab is NABL (National Accreditation Board for Testing and Calibration Laboratories) accredited. "
                    "Look for 'NABL Accredited', 'NABL Certified', or a NABL logo on the report. "
                    "Return 'YES', 'NO', or null if not determinable."
    )
    lab_id: ConfidenceField = Field(
        description="Lab's accreditation or registration ID if present. "
                    "E.g. 'KA-NABL-1234'. May appear near the NABL accreditation mark. "
                    "Set to null if not present."
    )
    patient_name: ConfidenceField = Field(
        description="Full name of the patient as written on the report. "
                    "Usually appears under 'Patient:' or 'Name:'."
    )
    patient_age: ConfidenceField = Field(
        description="Patient's age as written on the report. "
                    "May be combined with gender as 'Age/Sex: 39 / Male'. "
                    "Capture age and unit (years/months) if present."
    )
    patient_gender: ConfidenceField = Field(
        description="Patient's gender as written on the report. "
                    "Normalize to 'M' or 'F' in output."
    )
    referring_doctor: ConfidenceField = Field(
        description="Name of the doctor who ordered the tests. "
                    "Usually labeled 'Ref Doctor:', 'Referred By:', or 'Consulting Physician:'. "
                    "May be absent — set to null if not present."
    )
    sample_date: ConfidenceField = Field(
        description="Date the biological sample was collected from the patient. "
                    "Usually labeled 'Sample Date:', 'Collection Date:', or 'Drawn On:'. "
                    "Normalize to ISO format YYYY-MM-DD if possible."
    )
    report_date: ConfidenceField = Field(
        description="Date the report was generated or authorized by the pathologist. "
                    "Usually labeled 'Report Date:' or 'Reported On:'. "
                    "Normalize to ISO format YYYY-MM-DD if possible."
    )
    sample_id: ConfidenceField = Field(
        description="Unique sample or barcode ID assigned by the lab. "
                    "E.g. 'PD-2024-18723'. Used for traceability. "
                    "Set to null if not present."
    )
    test_results: List[LabTestResult] = Field(
        description="Complete list of all test results in the report. "
                    "For panel tests (e.g. CBC, LFT, KFT), extract each parameter as a separate entry. "
                    "Include both numeric and qualitative results."
    )
    remarks: ConfidenceField = Field(
        description="Any interpretive remarks, clinical notes, or recommendations provided by the pathologist. "
                    "E.g. 'WBC count is towards upper normal limit. Clinical correlation advised.' "
                    "Set to null if no remarks are present."
    )
    pathologist_name: ConfidenceField = Field(
        description="Full name and qualification of the pathologist or radiologist who authorized the report. "
                    "E.g. 'Dr. Meena Pillai, MD (Pathology)'. "
                    "Usually appears at the bottom of the report with a signature."
    )
    pathologist_registration: ConfidenceField = Field(
        description="Medical council registration number of the pathologist. "
                    "Follows state-specific formats: e.g. 'KA/89012/2018'. "
                    "May be absent on some reports — set to null if not present."
    )


class PharmacyMedicineItem(BaseModel):
    name: ConfidenceField = Field(
        description="Full name of the medicine as printed on the pharmacy bill. "
                    "E.g. 'Paracetamol 650', 'Vitamin C 500', 'Metformin 500mg SR'. "
                    "Capture brand name and strength exactly as written."
    )
    batch_number: ConfidenceField = Field(
        description="Manufacturer's batch or lot number for this medicine. "
                    "E.g. 'A2341', 'B7821'. Used for traceability and fraud detection. "
                    "Set to null if not present."
    )
    expiry_date: ConfidenceField = Field(
        description="Expiry date of the medicine batch as printed on the bill. "
                    "Usually in MM/YY or MM/YYYY format. E.g. '03/26', '06/2026'. "
                    "Flag if the expiry date is in the past relative to the bill date."
    )
    quantity: ConfidenceField = Field(
        description="Number of units (tablets, capsules, strips, bottles) purchased. "
                    "E.g. '15', '10', '2 strips'. Capture the unit if written."
    )
    mrp: ConfidenceField = Field(
        description="Maximum Retail Price per unit of the medicine in INR, as printed on the bill. "
                    "E.g. '2.50', '4.00'. This is the per-unit price before quantity multiplication."
    )
    amount: ConfidenceField = Field(
        description="Total amount charged for this medicine line item in INR (quantity × MRP minus any item-level discount). "
                    "E.g. '37.50', '40.00'. This is the most critical field per line item."
    )


class PharmacyBillDocument(BaseModel):
    pharmacy_name: ConfidenceField = Field(
        description="Name of the pharmacy or medical store issuing the bill. "
                    "E.g. 'Health First Pharmacy', 'MedPlus'. "
                    "Usually appears at the top of the bill."
    )
    drug_license_number: ConfidenceField = Field(
        description="Drug licence number of the pharmacy, mandatory for all licensed pharmacies in India. "
                    "Format varies by state, e.g. 'KA-BLR-XXXX'. "
                    "This field is a key identifier that distinguishes a pharmacy bill from other bill types."
    )
    bill_number: ConfidenceField = Field(
        description="Unique bill number assigned by the pharmacy. "
                    "E.g. 'HFP-24-09821'. Usually labeled 'Bill No:' or 'Invoice No:'."
    )
    issue_date: ConfidenceField = Field(
        description="Date the pharmacy bill was issued. "
                    "Normalize to ISO format YYYY-MM-DD if possible."
    )
    patient_name: ConfidenceField = Field(
        description="Name of the patient for whom the medicines were purchased. "
                    "May be labeled 'Patient:' or 'Customer Name:'. "
                    "Set to null if not present on the bill."
    )
    prescribing_doctor: ConfidenceField = Field(
        description="Name of the doctor who issued the prescription for these medicines. "
                    "Usually labeled 'Dr:' or 'Prescribed By:'. "
                    "Set to null if not mentioned on the bill."
    )
    medicines: List[PharmacyMedicineItem] = Field(
        description="Complete list of all medicines on the pharmacy bill. "
                    "Each entry captures name, batch number, expiry date, quantity, MRP, and amount. "
                    "Extract every line item, even if partially legible."
    )
    subtotal: ConfidenceField = Field(
        description="Sum of all medicine line item amounts before discounts, in INR. "
                    "Usually labeled 'Subtotal:' or 'Gross Amount:'."
    )
    discount: ConfidenceField = Field(
        description="Total discount applied on the bill in INR or percentage. "
                    "E.g. '-3.88' or '5%'. "
                    "Set to null if no discount is applied."
    )
    net_amount: ConfidenceField = Field(
        description="Final amount payable after discounts, in INR. "
                    "Usually labeled 'Net Amount:', 'Total:', or 'Amount Payable:'. "
                    "This is the most critical field on the pharmacy bill."
    )
    pharmacist_name: ConfidenceField = Field(
        description="Name of the licensed pharmacist who dispensed the medicines. "
                    "Usually appears at the bottom of the bill with a stamp. "
                    "Set to null if not present."
    )



# ---------------------------------------------------------------------------
# Union helper
# ---------------------------------------------------------------------------

DOCUMENT_MODEL_MAP = {
    "PRESCRIPTION": PrescriptionDocument,
    "HOSPITAL_BILL": HospitalBillDocument,
    "LAB_REPORT": LabReportDocument,
    "PHARMACY_BILL": PharmacyBillDocument,
}
