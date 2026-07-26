# Bhoomi Rakshak - Crop Insurance Claim Intake

Bhoomi Rakshak is a local full-stack web application designed for a block office to intake crop insurance claims. It validates claims against a village register, uses rule-based checks to catch simple discrepancies, and employs a Machine Learning model to detect near-duplicate claims on the fly. 

## Requirements
- Python 3.11+
- Flask
- Scikit-Learn
- Jellyfish (for string similarity metrics)

To install dependencies:
```bash
pip install flask scikit-learn jellyfish
```

## Running the Application
1. **Initialize Data:** `python seed.py` (Generates synthetic DB and ground truth).
2. **Train Model:** `python train_model.py` (Trains the scikit-learn LogisticRegression model).
3. **Start Server:** `python app.py`
4. **Access the App:** Open `http://localhost:5000` in your browser.

## Database Schema Diagram

```text
+----------------+       +-------------------+       +------------------+
| cultivators    |       | survey_numbers    |       | crops            |
+----------------+       +-------------------+       +------------------+
| id (PK)        |<----+-| survey_no (PK)    |   +-->| id (PK)          |
| name           |       | village           |   |   | name             |
+----------------+       | extent            |   |   +------------------+
                         | crop_id (FK)      |>--+
                         | cultivator_id (FK)|
                         +-------------------+

+------------------+       +--------------------+      +------------------+
| claims           |       | flags              |      | decisions        |
+------------------+       +--------------------+      +------------------+
| id (PK)          |<---+--| id (PK)            |  +---| id (PK)          |
| survey_no        |    |  | claim_id (FK)      |  |   | claim_id (FK, UQ)|
| cultivator_name  |    |  | reason             |  |   | officer_name     |
| claimed_crop     |    |  | matched_claim_id   |  |   | verdict          |
| claimed_extent   |    |  | confidence         |  |   | remark           |
| status           |    |  +--------------------+  |   | created_at       |
| locked_by        |    +--------------------------+   +------------------+
| locked_at        |
| created_at       |
+------------------+
```

## API Documentation

### 1. `GET /api/survey/<survey_no>`
Fetches the ground-truth data from the register for a survey number.
**Response:** `200 OK`
```json
{
  "survey_no": "1234",
  "village": "Palampur",
  "extent": 5.5,
  "crop": "Wheat",
  "cultivator_name": "Ramesh Kumar"
}
```
**Error Response:** `404 Not Found` if survey number does not exist.

### 2. `POST /api/claims`
Validates a new claim against the register, runs rule-based checks and the ML model, and saves the claim.
**Request Body:**
```json
{
  "survey_no": "1234",
  "cultivator_name": "Ramesh K",
  "claimed_crop": "Wheat",
  "claimed_extent": 5.5
}
```
**Response:** `201 Created`
```json
{
  "message": "Claim submitted successfully.",
  "claim_id": 15,
  "flags": [
    {
      "reason": "NEAR_DUPLICATE: Suspicious similarity to claim #12 (Confidence: 0.85)",
      "matched_claim_id": 12,
      "confidence": 0.85
    }
  ]
}
```

### 3. `GET /api/queue`
Retrieves a list of all claims that have at least one flag and have not yet been decided.
**Response:** Array of claims, each with an embedded array of `flags` (and `matched_claim_data` if applicable).

### 4. `POST /api/queue/<id>/lock`
Optimistically locks a claim for 5 minutes for a specific officer.
**Request Body:** `{"officer_name": "Officer Sharma"}`
**Responses:** 
- `200 OK` if locked successfully.
- `409 Conflict` if currently locked by someone else (within 5 minutes).

### 5. `POST /api/queue/<id>/decide`
Records an officer's final decision. Enforced structurally at the DB level with a UNIQUE constraint to prevent silent overwriting.
**Request Body:** 
```json
{
  "officer_name": "Officer Sharma",
  "verdict": "rejected",
  "remark": "Duplicate claim verified by calling the cultivator."
}
```
**Responses:**
- `200 OK`
- `409 Conflict` if a decision has already been recorded.

## Rule-Based Checks
When a claim is submitted, three deterministic checks execute before the ML inference:
1. **Duplicate Survey Check:** Flags the claim if another non-rejected claim exists in the system for the exact same survey number.
2. **Extent Check:** Flags the claim if the `claimed_extent` exceeds the recorded ground-truth `extent` for that survey number in the register.
3. **Crop Check:** Flags the claim if the `claimed_crop` does not exactly match the recorded crop in the register.
*(Note: A claim can accumulate multiple flags simultaneously without short-circuiting).*

## Near-Duplicate Similarity Model (ML)
To catch fraudulent claims that exploit digit transposition and name variations, a `LogisticRegression(class_weight="balanced")` model evaluates the new claim against existing claims.

### Engineered Features
1. **Survey Number Similarity:** Jaro-Winkler string similarity between the survey numbers.
2. **Transposed Digits (Boolean):** 1 if the survey numbers are exactly one adjacent digit transposition apart (e.g., "145" vs "154").
3. **Name Similarity:** Jaro-Winkler string similarity between the normalized cultivator names.
4. **Crop Match (Boolean):** 1 if the claimed crops are identical.
5. **Extent Closeness:** A normalized bounded difference `1.0 - abs(e1 - e2) / max(e1, e2, 1.0)`.

### Model Evaluation Figures
Evaluated using Leave-One-Out Cross Validation against a heavily skewed dataset of planted synthetic data:
- **Planted near-duplicate pairs caught:** 5 out of 5 (100% Recall on target edge cases)
- **False positive pairs wrongly flagged:** 42 out of 1760 non-duplicate pairs scanned.

## How a Flag Becomes a Decision
1. **Intake:** The clerk inputs the claim; the system flags it.
2. **Queueing:** The claim lands in the Verification Queue via `GET /api/queue` with all its generated flags.
3. **Locking:** An officer reviews the queue and clicks "Lock for Review" (`POST /api/queue/<id>/lock`). This prevents race conditions and blocks other officers from deciding the same claim for 5 minutes.
4. **Comparison & Decision:** The UI shows a side-by-side comparison of the new claim vs the matched claim (if applicable). The officer is required to input a remark and chooses "Approve" or "Reject" (`POST /api/queue/<id>/decide`), permanently marking the claim's status.

---
> **Submission Requirements Checklist:**
> - [ ] Add screenshots of the Intake Screen.
> - [ ] Add screenshots of a Flagged Claim on the Intake Screen.
> - [ ] Add screenshots of the Verification Queue.
> - [ ] Add a short screen recording following one duplicate claim from entry to rejection against the live running app.
