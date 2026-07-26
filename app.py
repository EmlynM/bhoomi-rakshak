import sqlite3
import datetime
import os
import joblib
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
import jellyfish
from train_model import compute_features

app = Flask(__name__, static_folder='static', static_url_path='')
DB_FILE = 'bhoomi.db'
MODEL_FILE = 'model.pkl'

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# Helper: ML Model inference
def score_claim_against_others(new_claim, cursor):
    cursor.execute("SELECT * FROM claims WHERE id != ?", (new_claim['id'],))
    existing_claims = cursor.fetchall()
    
    if not existing_claims or not os.path.exists(MODEL_FILE):
        return None
    
    try:
        model = joblib.load(MODEL_FILE)
    except Exception as e:
        print("Error loading model:", e)
        return None
        
    best_match = None
    highest_prob = 0.0
    
    # We want a high threshold for near duplicates to avoid spamming the officers
    THRESHOLD = 0.7 
    
    for ec in existing_claims:
        ec_dict = dict(ec)
        features = compute_features(new_claim, ec_dict)
        
        # predict_proba returns [[prob_0, prob_1]]
        prob = model.predict_proba(np.array([features]))[0][1]
        
        if prob > highest_prob:
            highest_prob = prob
            best_match = ec_dict
            
    if highest_prob >= THRESHOLD and best_match:
        return best_match, highest_prob
    
    return None, 0.0

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/queue')
def queue_page():
    return send_from_directory('static', 'queue.html')

@app.route('/api/survey/<survey_no>', methods=['GET'])
def get_survey(survey_no):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.survey_no, s.village, s.extent, c.name as crop, cul.name as cultivator_name
        FROM survey_numbers s
        JOIN crops c ON s.crop_id = c.id
        JOIN cultivators cul ON s.cultivator_id = cul.id
        WHERE s.survey_no = ?
    """, (survey_no,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return jsonify(dict(row))
    else:
        return jsonify({"error": "Survey number not found in register."}), 404

@app.route('/api/claims', methods=['POST'])
def create_claim():
    data = request.json
    survey_no = data.get('survey_no')
    cultivator_name = data.get('cultivator_name')
    claimed_crop = data.get('claimed_crop')
    claimed_extent = data.get('claimed_extent')
    
    if not all([survey_no, cultivator_name, claimed_crop, claimed_extent]):
        return jsonify({"error": "Missing required fields"}), 400
        
    try:
        claimed_extent = float(claimed_extent)
        if claimed_extent <= 0:
            return jsonify({"error": "Claimed extent must be greater than 0"}), 400
    except ValueError:
        return jsonify({"error": "Invalid claimed extent"}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    # Validate against register
    cursor.execute("""
        SELECT s.survey_no, s.village, s.extent, c.name as crop, cul.name as cultivator_name
        FROM survey_numbers s
        JOIN crops c ON s.crop_id = c.id
        JOIN cultivators cul ON s.cultivator_id = cul.id
        WHERE s.survey_no = ?
    """, (survey_no,))
    register = cursor.fetchone()
    
    if not register:
        conn.close()
        return jsonify({"error": "Survey number not found in register. Claim rejected."}), 400
        
    # Insert claim
    cursor.execute("""
        INSERT INTO claims (survey_no, cultivator_name, claimed_crop, claimed_extent)
        VALUES (?, ?, ?, ?)
    """, (survey_no, cultivator_name, claimed_crop, claimed_extent))
    claim_id = cursor.lastrowid
    
    new_claim = {
        'id': claim_id,
        'survey_no': survey_no,
        'cultivator_name': cultivator_name,
        'claimed_crop': claimed_crop,
        'claimed_extent': claimed_extent
    }
    
    flags = []
    
    # Task 3: Rule-based checks
    
    # 1. Duplicate survey
    cursor.execute("""
        SELECT id FROM claims 
        WHERE survey_no = ? AND id != ? AND status != 'REJECTED'
    """, (survey_no, claim_id))
    dup_survey = cursor.fetchone()
    if dup_survey:
        flags.append({
            "reason": "EXACT_SURVEY_DUPLICATE: Another non-rejected claim already exists for this survey number.",
            "matched_claim_id": dup_survey['id']
        })
        
    # 2. Extent exceeds register
    if claimed_extent > register['extent']:
        flags.append({
            "reason": f"EXTENT_EXCEEDS_REGISTER: Claimed extent ({claimed_extent}) exceeds recorded extent ({register['extent']}).",
            "matched_claim_id": None
        })
        
    # 3. Crop mismatch
    if claimed_crop != register['crop']:
        flags.append({
            "reason": f"CROP_MISMATCH: Claimed crop ({claimed_crop}) does not match recorded crop ({register['crop']}).",
            "matched_claim_id": None
        })
        
    # Task 4: Near-duplicate ML check
    match, prob = score_claim_against_others(new_claim, cursor)
    if match:
        flags.append({
            "reason": f"NEAR_DUPLICATE: Suspicious similarity to claim #{match['id']} (Confidence: {prob:.2f})",
            "matched_claim_id": match['id'],
            "confidence": float(prob)
        })
        
    # Insert flags
    for f in flags:
        cursor.execute("""
            INSERT INTO flags (claim_id, reason, matched_claim_id, confidence)
            VALUES (?, ?, ?, ?)
        """, (claim_id, f['reason'], f.get('matched_claim_id'), f.get('confidence')))
        
    conn.commit()
    conn.close()
    
    return jsonify({
        "message": "Claim submitted successfully.",
        "claim_id": claim_id,
        "flags": flags
    }), 201

@app.route('/api/queue', methods=['GET'])
def get_queue():
    conn = get_db()
    cursor = conn.cursor()
    
    # Find claims that have flags but no decision yet
    cursor.execute("""
        SELECT DISTINCT c.id, c.survey_no, c.cultivator_name, c.claimed_crop, c.claimed_extent,
               c.status, c.locked_by, c.locked_at
        FROM claims c
        JOIN flags f ON c.id = f.claim_id
        LEFT JOIN decisions d ON c.id = d.claim_id
        WHERE d.id IS NULL
        ORDER BY c.created_at ASC
    """)
    claims = [dict(r) for r in cursor.fetchall()]
    
    # Attach flags
    for c in claims:
        cursor.execute("SELECT id, reason, matched_claim_id, confidence FROM flags WHERE claim_id = ?", (c['id'],))
        c['flags'] = [dict(r) for r in cursor.fetchall()]
        
        # Attach matched claims data if present
        for f in c['flags']:
            if f['matched_claim_id']:
                cursor.execute("SELECT * FROM claims WHERE id = ?", (f['matched_claim_id'],))
                m = cursor.fetchone()
                if m:
                    f['matched_claim_data'] = dict(m)
                    
    conn.close()
    return jsonify(claims)

@app.route('/api/queue/<int:claim_id>/lock', methods=['POST'])
def lock_claim(claim_id):
    data = request.json
    officer_name = data.get('officer_name')
    if not officer_name:
        return jsonify({"error": "Officer name required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT locked_by, locked_at FROM claims WHERE id = ?", (claim_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({"error": "Claim not found"}), 404
        
    now = datetime.datetime.utcnow()
    
    # Check if currently locked
    if row['locked_by'] and row['locked_at']:
        locked_at = datetime.datetime.strptime(row['locked_at'], "%Y-%m-%d %H:%M:%S.%f")
        # 5 minutes TTL
        if row['locked_by'] != officer_name and (now - locked_at).total_seconds() < 300:
            conn.close()
            return jsonify({"error": f"Claim is currently locked by {row['locked_by']}"}), 409
            
    cursor.execute("UPDATE claims SET locked_by = ?, locked_at = ? WHERE id = ?", (officer_name, str(now), claim_id))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Claim locked successfully"})

@app.route('/api/queue/<int:claim_id>/decide', methods=['POST'])
def decide_claim(claim_id):
    data = request.json
    officer_name = data.get('officer_name')
    verdict = data.get('verdict')
    remark = data.get('remark')
    
    if not all([officer_name, verdict, remark]):
        return jsonify({"error": "Officer name, verdict, and remark are required"}), 400
        
    if verdict not in ['approved', 'rejected']:
        return jsonify({"error": "Invalid verdict"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Enforce unique constraint via database
        cursor.execute("""
            INSERT INTO decisions (claim_id, officer_name, verdict, remark)
            VALUES (?, ?, ?, ?)
        """, (claim_id, officer_name, verdict, remark))
        
        cursor.execute("UPDATE claims SET status = ? WHERE id = ?", (verdict.upper(), claim_id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({"error": "A decision has already been recorded for this claim."}), 409
        
    conn.close()
    return jsonify({"message": f"Claim {verdict} successfully."})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
