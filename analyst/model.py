import json
import sys
import pandas as pd
import numpy as np
from kmodes.kmodes import KModes
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import LeaveOneOut, StratifiedKFold, cross_val_predict
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
from sklearn.preprocessing import MultiLabelBinarizer

N_CLUSTERS= 5
LOOCV_MAX_N= 200

def choose_cv_strategy(n_samples):
    if n_samples <= LOOCV_MAX_N:
        return LeaveOneOut(),"Leave-One-Out CV"
    else:
        return StratifiedKFold(n_splits=5, shuffle=True, random_state=42),"Stratified 5-Fold CV"

def build_features_target(df,use_kmodes_cluster=False):
    def has_outcomes(row):
        outcomes = row.get("outcomes")
        if not outcomes or (isinstance(outcomes, list) and len(outcomes) >= 2):
            return 1
        return 0
    y=df.apply(has_outcomes,axis=1).values

    domain_encoded= pd.get_dummies(df["domain"], prefix="domain")
    region_encoded= pd.get_dummies(df["region"],prefix="region")

    def ensure_list(val):
        if isinstance(val,list):
            return val
        return []
    tech_lists= df["technologies"].apply(ensure_list)
    mlb= MultiLabelBinarizer()
    tech_matrix= pd.DataFrame(mlb.fit_transform(tech_lists),columns=[f"tech_{c}" for c in mlb.classes_],index=df.index)

    feature_frames = [domain_encoded, region_encoded, tech_matrix]
    km_model= None

    if use_kmodes_cluster:
        cluster_input= df[["domain","region"]].astype(str)
        n_clusters = min(N_CLUSTERS, len(df) - 1)
        km_model = KModes(n_clusters=n_clusters, init="Huang", n_init=5, random_state=42, verbose=0)
        cluster_labels = km_model.fit_predict(cluster_input)
        cluster_encoded = pd.get_dummies(
            pd.Series(cluster_labels, index=df.index), prefix="win_theme_cluster"
            )
        feature_frames.append(cluster_encoded)

    X = pd.concat(feature_frames, axis=1)
    return X, y, mlb, km_model

def evaluate_model(X, y, model=None, model_name="Logistic Regression"):
    n = len(y)
    n_pos = sum(y)
    n_neg = n - n_pos
    print(f"Total records: {n} (positive/outcomes: {n_pos}, negative/missing: {n_neg})")

    if n_pos == 0 or n_neg == 0:
        print("\nWARNING: The target variable contains only one class (all 0 or all 1).")
        return None
    if model is None:
        model = LogisticRegression(max_iter=1000)
    cv_strategy, cv_name = choose_cv_strategy(n)
    print(f"Model: {model_name} | CV Strategy: {cv_name} (n={n})")

    y_pred = []
    
    for train_idx, test_idx in cv_strategy.split(X, y):
        X_train, y_train = X.iloc[train_idx], y[train_idx]
        X_test = X.iloc[test_idx]
        
        if len(np.unique(y_train)) == 1:
            y_pred.append(y_train[0])
        else:
            from sklearn.base import clone
            cloned_model = clone(model)
            cloned_model.fit(X_train, y_train)
            y_pred.append(cloned_model.predict(X_test)[0])    

    acc = accuracy_score(y, y_pred)
    cm = confusion_matrix(y, y_pred)

    print(f"\n--- {cv_name} Results ({model_name}) ---")
    print(f"Accuracy: {acc:.2f}")
    print(f"Confusion matrix:\n{cm}")
    print(f"\nClassification report:\n{classification_report(y, y_pred, zero_division=0)}")

    majority_class = 1 if n_pos >= n_neg else 0
    baseline_acc= max(n_pos, n_neg) / n
    print(f"Baseline predict '{majority_class}'): {baseline_acc:.2f} accuracy")

    if acc <= baseline_acc:
        print(
            "\nWARNING: The model is not performing better than the baseline. "
            "This is expected with such a small dataset "
            "and the model may not have enough data to learn a real pattern. "
            "Results should be interpreted with caution.")
    else:
        print(
            f"\nModel, with accuracy {acc:.2f}, is performing better than the baseline accuracy of {baseline_acc:.2f}. "
            "However, since n is very small, this difference may not be statistically significant — more data should be used to validate the results."
        )
    return {"accuracy": acc, "baseline_accuracy": baseline_acc, "confusion_matrix": cm.tolist()}

def train_final_model(X, y):
    model = LogisticRegression(max_iter=1000)
    model.fit(X, y)
    return model


def predict_new_opportunity(model, feature_columns, mlb, domain, region, technologies, km_model=None):
    row = pd.DataFrame([{col: 0 for col in feature_columns}])

    domain_col = f"domain_{domain}"
    region_col = f"region_{region}"

    warnings = []
    
    if domain_col in row.columns:
        row[domain_col]= 1
    else:
        warnings.append(f"'{domain}' domain didn't show up in training data — model is blind to this domain.")

    if region_col in row.columns:
        row[region_col]= 1
    else:
        warnings.append(f"'{region}' region didnt show up in training data — model is blind to this region.")

    for tech in technologies:
        tech_col = f"tech_{tech}"
        if tech_col in row.columns:
            row[tech_col] = 1
        else:
            warnings.append(f"'{tech}' technology didn't show up in training data — model is blind to this technology.")

    assigned_cluster = None
    if km_model is not None:
        try:
            assigned_cluster = int(km_model.predict(pd.DataFrame([{"domain": domain, "region": region}]))[0])
            cluster_col = f"win_theme_cluster_{assigned_cluster}"
            if cluster_col in row.columns:
                row[cluster_col] = 1
            else:
                warnings.append(f"There is no matching feature column for assigned cluster ({assigned_cluster}).")
        except Exception as e:
            warnings.append(f"K-Modes cluster assignment failed: {e}")

    proba = model.predict_proba(row)[0][1] 
    proba = model.predict_proba(row)[0][1] 

    penalty_per_warning = 0.15
    total_penalty = len(warnings) * penalty_per_warning
    
    adjusted_proba = max(0.0, proba - total_penalty)

    result = {
        "domain": domain,
        "region": region,
        "technologies": technologies,
        "base_model_score": round(float(proba), 3),  # Modelin ham tahmini
        "evidence_score": round(float(adjusted_proba), 3),  # Cezalandırılmış gerçekçi skor
        "warnings": warnings,
    }
    
    if assigned_cluster is not None:
        result["win_theme_cluster"] = assigned_cluster

    return result
def analyze_rfp(domain, region, technologies, corpus_path="caseforge-testdata/records/corpus.json"):
    
    import json
    import pandas as pd
    
    try:
        with open(corpus_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.json_normalize(data)
    except FileNotFoundError:
        return {"error": f"Corpus dosyası bulunamadı: {corpus_path}"}

    X, y, mlb, _ = build_features_target(df, use_kmodes_cluster=False)
    final_model = train_final_model(X, y)
    feature_columns = list(X.columns)

    # Tahmin yap ve sonucu (JSON/Sözlük olarak) Flow'a geri döndür
    result = predict_new_opportunity(
        model=final_model, 
        feature_columns=feature_columns, 
        mlb=mlb, 
        domain=domain, 
        region=region, 
        technologies=technologies
    )
    
    return result

if __name__ == "__main__":
    JSON_PATH = "caseforge-testdata/records/corpus.json"  

    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: '{JSON_PATH}' not found.")
        sys.exit(1)

    df = pd.json_normalize(data)
    print(f"Data set loaded: {len(df)} records\n")

    print("=" * 60)
    print("MODEL A — domain + region + technologies")
    print("=" * 60)
    X_a, y_a, mlb_a, _ = build_features_target(df, use_kmodes_cluster=False)
    results_a = evaluate_model(X_a, y_a)

    print("\n" + "=" * 60)
    print("MODEL B — Model A + K-Modes win-theme cluster")
    print("=" * 60)
    X_b, y_b, mlb_b, km_model = build_features_target(df, use_kmodes_cluster=True)
    results_b = evaluate_model(X_b, y_b)

    print("\n" + "=" * 60)
    print("MODEL COMPARISON — Model A vs Model B")
    print("=" * 60)
    if results_a and results_b:
        diff = results_b["accuracy"] - results_a["accuracy"]
        print(f"Model A (without cluster) accuracy: {results_a['accuracy']:.2f}")
        print(f"Model B (with cluster) accuracy: {results_b['accuracy']:.2f}")

        if abs(diff) < 0.05:
            print(
                "\nAdding the K-Modes win-theme cluster practically made no difference. This is because the clusters are already derived from domain+region information. So the model already sees the same information."
            )
        else:
            print(f"\nDifference: {diff:+.2f} — adding the cluster {'improved' if diff > 0 else 'worsened'} the model.")

    print("\n" + "=" * 60)
    print("MODEL C — Random Forest Classifier")
    print("=" * 60)
    rf_model = RandomForestClassifier(n_estimators=100, max_depth=3, random_state=42)
    results_c = evaluate_model(X_a, y_a, model=rf_model, model_name="Random Forest")

    print("\n" + "=" * 60)
    print("ALGORITHM COMPARISON — Logistic Regression vs Random Forest")
    print("=" * 60)
    if results_a and results_c:
        print(f"Logistic Regression accuracy: {results_a['accuracy']:.2f}")
        print(f"Random Forest accuracy      : {results_c['accuracy']:.2f}")
        diff_rf = results_c["accuracy"] - results_a["accuracy"]
        
        if abs(diff_rf) < 0.05:
            print(
                "\nRandom Forest did not make a significant difference compared "
                "to Logistic Regression. Tree-based models add complexity without providing "
                "extra benefit on small datasets (n<100). We are opting for the simplest "
                "approach (Logistic Regression).")
        else:
            print(f"\nDifference: {diff_rf:+.2f}")

    print("\n" + "=" * 60)
    print("TRAINING FINAL MODEL (Model A / Logistic Regression, using all data)")
    print("=" * 60)
    final_model = train_final_model(X_a, y_a)
    feature_columns = list(X_a.columns)

    print("\n--- Example Prediction 1: Known Patterns (New RFP) ---")
    example= predict_new_opportunity(
        final_model, feature_columns, mlb_a,
        domain="core banking", region="UK", technologies=["Java", "Kafka"],
    )
    print(json.dumps(example, indent=2, ensure_ascii=False))

    print("\n--- Example Prediction 2: Unknown Combination (Unknown Point) ---")
    example2 = predict_new_opportunity(
        final_model, feature_columns, mlb_a,
        domain="quantum computing", region="JP", technologies=["Qiskit"],
    )
    print(json.dumps(example2, indent=2, ensure_ascii=False))