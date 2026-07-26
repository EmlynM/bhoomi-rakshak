import sqlite3
import json
import random
import os

DB_FILE = 'bhoomi.db'
SCHEMA_FILE = 'schema.sql'
GROUND_TRUTH_FILE = 'ground_truth.json'

def reset_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    
    with open(SCHEMA_FILE, 'r') as f:
        schema = f.read()
    
    conn = sqlite3.connect(DB_FILE)
    conn.executescript(schema)
    return conn

def seed():
    conn = reset_db()
    cursor = conn.cursor()

    # Crops
    crops = ['Wheat', 'Rice', 'Cotton', 'Sugarcane', 'Maize', 'Soybean']
    for crop in crops:
        cursor.execute("INSERT INTO crops (name) VALUES (?)", (crop,))
    
    # Cultivators (Base names)
    base_names = [
        "Ramesh Kumar", "Suresh Patel", "Anita Devi", "Vikram Singh", 
        "Pooja Sharma", "Amitabh Bach", "Rahul Gandhi", "Narendra Modi", 
        "Sunil Chhetri", "Virat Kohli", "Rohit Sharma", "MS Dhoni",
        "Kiran Bedi", "Lata Mangeshkar", "Ratan Tata", "Mukesh Ambani",
        "Anil Kapoor", "Salman Khan", "Shahrukh Khan", "Aamir Khan",
        "Gita Phogat", "Mary Kom", "Sania Mirza", "Saina Nehwal",
        "Priyanka Chopra", "Deepika Padukone", "Ranveer Singh", "Ranbir Kapoor"
    ]
    
    cultivators = []
    for name in base_names:
        cursor.execute("INSERT INTO cultivators (name) VALUES (?)", (name,))
        cultivators.append({'id': cursor.lastrowid, 'name': name})

    villages = ['Palampur', 'Ramgarh', 'Malgudi', 'Champak', 'Bhimpur']

    # We need to generate 40-45 survey numbers.
    # Let's create some normal ones, and some transposed pairs for near-duplicates.
    survey_register = []
    
    # Generate 5 transposed pairs (10 survey numbers) for near-duplicate testing
    transposed_pairs = [
        ("145", "154"), ("289", "298"), ("310", "301"), ("456", "465"), ("782", "728")
    ]
    
    near_dup_register_pairs = []
    for s1, s2 in transposed_pairs:
        cultivator = random.choice(cultivators)
        village = random.choice(villages)
        crop_id = random.randint(1, len(crops))
        extent = round(random.uniform(2.0, 10.0), 2)
        
        # Insert s1
        cursor.execute(
            "INSERT INTO survey_numbers (survey_no, village, extent, crop_id, cultivator_id) VALUES (?, ?, ?, ?, ?)",
            (s1, village, extent, crop_id, cultivator['id'])
        )
        survey_register.append({"survey_no": s1, "extent": extent, "crop_id": crop_id, "crop": crops[crop_id-1], "cultivator": cultivator})
        
        # Insert s2 (similar extent, same crop, same cultivator, same village)
        extent2 = round(extent + random.uniform(-0.5, 0.5), 2)
        if extent2 <= 0: extent2 = extent
        cursor.execute(
            "INSERT INTO survey_numbers (survey_no, village, extent, crop_id, cultivator_id) VALUES (?, ?, ?, ?, ?)",
            (s2, village, extent2, crop_id, cultivator['id'])
        )
        survey_register.append({"survey_no": s2, "extent": extent2, "crop_id": crop_id, "crop": crops[crop_id-1], "cultivator": cultivator})
        
        near_dup_register_pairs.append((s1, s2, cultivator['name']))
        
    # Generate remaining 30-35 normal survey numbers
    used_surveys = set([s for pair in transposed_pairs for s in pair])
    while len(survey_register) < 42:
        s_no = str(random.randint(1000, 9999))
        if s_no in used_surveys:
            continue
        used_surveys.add(s_no)
        
        cultivator = random.choice(cultivators)
        village = random.choice(villages)
        crop_id = random.randint(1, len(crops))
        extent = round(random.uniform(1.0, 15.0), 2)
        
        cursor.execute(
            "INSERT INTO survey_numbers (survey_no, village, extent, crop_id, cultivator_id) VALUES (?, ?, ?, ?, ?)",
            (s_no, village, extent, crop_id, cultivator['id'])
        )
        survey_register.append({"survey_no": s_no, "extent": extent, "crop_id": crop_id, "crop": crops[crop_id-1], "cultivator": cultivator})

    # Claims generation
    claims_to_insert = []
    ground_truth_duplicates = [] # list of (claim_id_1, claim_id_2, type)
    
    # 1. Clean claims (~30)
    normal_register = [r for r in survey_register if r['survey_no'] not in used_surveys or len(r['survey_no']) == 4]
    for _ in range(30):
        reg = random.choice(normal_register)
        claims_to_insert.append({
            "survey_no": reg['survey_no'],
            "cultivator_name": reg['cultivator']['name'],
            "claimed_crop": reg['crop'],
            "claimed_extent": round(reg['extent'] * random.uniform(0.5, 1.0), 2) # valid extent
        })
        
    # 2. Extent exceeds (~5)
    for _ in range(5):
        reg = random.choice(normal_register)
        claims_to_insert.append({
            "survey_no": reg['survey_no'],
            "cultivator_name": reg['cultivator']['name'],
            "claimed_crop": reg['crop'],
            "claimed_extent": round(reg['extent'] * random.uniform(1.1, 2.0), 2) # invalid extent
        })
        
    # 3. Crop mismatch (~5)
    for _ in range(5):
        reg = random.choice(normal_register)
        wrong_crop = random.choice([c for c in crops if c != reg['crop']])
        claims_to_insert.append({
            "survey_no": reg['survey_no'],
            "cultivator_name": reg['cultivator']['name'],
            "claimed_crop": wrong_crop,
            "claimed_extent": round(reg['extent'] * random.uniform(0.5, 1.0), 2)
        })

    # To track IDs before inserting into DB, we'll assign them sequentially
    next_claim_id = len(claims_to_insert) + 1
    
    # 4. Exact duplicate pairs (~5 pairs)
    for _ in range(5):
        reg = random.choice(normal_register)
        # Original claim
        c1_id = next_claim_id
        next_claim_id += 1
        claims_to_insert.append({
            "id": c1_id,
            "survey_no": reg['survey_no'],
            "cultivator_name": reg['cultivator']['name'],
            "claimed_crop": reg['crop'],
            "claimed_extent": round(reg['extent'], 2)
        })
        
        # Exact duplicate with slightly different name spelling
        c2_id = next_claim_id
        next_claim_id += 1
        name_variants = [
            reg['cultivator']['name'].replace("a", "aa"),
            reg['cultivator']['name'].replace("i", "ee"),
            reg['cultivator']['name'] + " Ji",
            reg['cultivator']['name'].upper()
        ]
        claims_to_insert.append({
            "id": c2_id,
            "survey_no": reg['survey_no'],
            "cultivator_name": random.choice(name_variants),
            "claimed_crop": reg['crop'],
            "claimed_extent": round(reg['extent'], 2)
        })
        ground_truth_duplicates.append({"claim_id_1": c1_id, "claim_id_2": c2_id, "type": "exact"})

    # 5. Near duplicate pairs (~5 pairs from the transposed ones)
    for s1, s2, c_name in near_dup_register_pairs:
        r1 = next((r for r in survey_register if r['survey_no'] == s1), None)
        r2 = next((r for r in survey_register if r['survey_no'] == s2), None)
        
        c1_id = next_claim_id
        next_claim_id += 1
        claims_to_insert.append({
            "id": c1_id,
            "survey_no": r1['survey_no'],
            "cultivator_name": c_name,
            "claimed_crop": r1['crop'],
            "claimed_extent": round(r1['extent'], 2)
        })
        
        c2_id = next_claim_id
        next_claim_id += 1
        name_variants = [
            c_name.replace("a", "aa"),
            c_name.replace("u", "oo"),
            c_name + " Rao",
            c_name.lower()
        ]
        claims_to_insert.append({
            "id": c2_id,
            "survey_no": r2['survey_no'],
            "cultivator_name": random.choice(name_variants),
            "claimed_crop": r2['crop'],
            "claimed_extent": round(r2['extent'], 2)
        })
        ground_truth_duplicates.append({"claim_id_1": c1_id, "claim_id_2": c2_id, "type": "near"})

    # Shuffle claims to make it realistic (so duplicates aren't always adjacent)
    # But keep their assigned IDs intact
    for i, c in enumerate(claims_to_insert):
        if 'id' not in c:
            c['id'] = i + 1

    random.shuffle(claims_to_insert)

    for c in claims_to_insert:
        cursor.execute(
            "INSERT INTO claims (id, survey_no, cultivator_name, claimed_crop, claimed_extent) VALUES (?, ?, ?, ?, ?)",
            (c['id'], c['survey_no'], c['cultivator_name'], c['claimed_crop'], c['claimed_extent'])
        )

    conn.commit()
    conn.close()

    with open(GROUND_TRUTH_FILE, 'w') as f:
        json.dump(ground_truth_duplicates, f, indent=4)

    print(f"Generated {len(survey_register)} survey numbers.")
    print(f"Generated {len(claims_to_insert)} claims.")
    print(f"Generated {len(ground_truth_duplicates)} planted duplicate pairs.")
    print("Database seeded successfully.")

if __name__ == '__main__':
    seed()
