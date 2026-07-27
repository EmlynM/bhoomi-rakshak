import sqlite3
import json
import jellyfish
import itertools
import numpy as np
from sklearn.linear_model import LogisticRegression
import joblib

DB_FILE = 'bhoomi.db'
GROUND_TRUTH_FILE = 'ground_truth.json'
MODEL_FILE = 'model.pkl'

def is_transposed(s1, s2):
    if len(s1) != len(s2) or s1 == s2:
        return 0
    diffs = [(i, c1, c2) for i, (c1, c2) in enumerate(zip(s1, s2)) if c1 != c2]
    if len(diffs) == 2:
        i, c1_a, c2_a = diffs[0]
        j, c1_b, c2_b = diffs[1]
        if j == i + 1 and c1_a == c2_b and c1_b == c2_a:
            return 1
    return 0

def compute_features(c1, c2):
    # c1, c2 are dictionaries: {survey_no, cultivator_name, claimed_crop, claimed_extent}
    
    # 1. character similarity between the two survey numbers
    survey_sim = jellyfish.jaro_winkler_similarity(c1['survey_no'], c2['survey_no'])
    
    # 2. specific boolean feature for "is one survey number the other with two adjacent digits transposed"
    transposed = is_transposed(c1['survey_no'], c2['survey_no'])
    
    # 3. character similarity between the two entered cultivator names
    name_sim = jellyfish.jaro_winkler_similarity(
        c1['cultivator_name'].lower(), c2['cultivator_name'].lower()
    )
    
    # 4. whether the claimed crop matches
    crop_match = 1 if c1['claimed_crop'] == c2['claimed_crop'] else 0
    
    # 5. how close the two claimed extents are, normalized
    max_extent = max(c1['claimed_extent'], c2['claimed_extent'], 1.0)
    extent_diff = abs(c1['claimed_extent'] - c2['claimed_extent'])
    extent_closeness = max(0.0, 1.0 - (extent_diff / max_extent))
    
    return [survey_sim, transposed, name_sim, crop_match, extent_closeness]

def load_data():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    claims = [dict(row) for row in conn.execute("SELECT * FROM claims")]
    conn.close()
    
    with open(GROUND_TRUTH_FILE, 'r') as f:
        ground_truth = json.load(f)
        
    positive_pairs = set()
    near_dup_pairs = set()
    for item in ground_truth:
        # Undirected pair
        pair = frozenset([item['claim_id_1'], item['claim_id_2']])
        positive_pairs.add(pair)
        if item.get('type') == 'near':
            near_dup_pairs.add(pair)
            
    return claims, positive_pairs, near_dup_pairs

def build_dataset():
    claims, positive_pairs, near_dup_pairs = load_data()
    
    X = []
    y = []
    pairs_info = [] # (id1, id2, is_near_dup)
    
    for c1, c2 in itertools.combinations(claims, 2):
        features = compute_features(c1, c2)
        pair = frozenset([c1['id'], c2['id']])
        
        is_pos = 1 if pair in positive_pairs else 0
        is_near = 1 if pair in near_dup_pairs else 0
        
        X.append(features)
        y.append(is_pos)
        pairs_info.append((c1['id'], c2['id'], is_near))
        
    return np.array(X), np.array(y), pairs_info

def train_and_evaluate():
    X, y, pairs_info = build_dataset()
    
    # Shuffle the dataset to ensure positive cases are distributed
    indices = np.arange(len(X))
    np.random.seed(42)
    np.random.shuffle(indices)
    X = X[indices]
    y = y[indices]
    pairs_info = [pairs_info[i] for i in indices]
    
    # Implement an 80/20 split
    split_idx = int(len(X) * 0.8)
    
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    pairs_info_test = pairs_info[split_idx:]
    
    model = LogisticRegression(class_weight='balanced', random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
        
    # Evaluate honest numbers
    near_dup_caught = 0
    total_near_dup = 0
    
    false_positives = 0
    total_negatives = 0
    
    for i in range(len(y_test)):
        actual = y_test[i]
        predicted = y_pred[i]
        is_near_dup = pairs_info_test[i][2]
        
        if is_near_dup:
            total_near_dup += 1
            if predicted == 1:
                near_dup_caught += 1
                
        if actual == 0:
            total_negatives += 1
            if predicted == 1:
                false_positives += 1
                
    print(f"--- Evaluation Results (80/20 Split) ---")
    print(f"Near-duplicate pairs caught in test set: {near_dup_caught} out of {total_near_dup}")
    print(f"False positive pairs wrongly flagged in test set: {false_positives} out of {total_negatives} non-duplicate pairs scanned")
    print("\n--- Why did the accuracy drop or behave erratically? ---")
    print("When we switch from Leave-One-Out (which evaluates on the entire dataset) to a strict")
    print("80/20 split, the evaluation metrics can drop or fluctuate significantly. Because our")
    print("'near-duplicate' positive cases are extremely rare, a random 80/20 split might place")
    print("very few of them in the test set, making the recall metric highly sensitive to missing")
    print("even a single one. It also reduces the training data, lowering the model's ability to generalize.")
    print("In small, highly imbalanced datasets, holding back 20% leads to high variance in metrics.")
    print("----------------------------------------------------------\n")
    
    # Train final model on all data and save
    final_model = LogisticRegression(class_weight='balanced', random_state=42)
    final_model.fit(X, y)
    joblib.dump(final_model, MODEL_FILE)
    print(f"Model saved to {MODEL_FILE}")

if __name__ == '__main__':
    train_and_evaluate()
