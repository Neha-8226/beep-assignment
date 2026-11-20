"""Human Ground-Truth Evaluation Engine.

Calculates:
1. Role classification accuracy (%).
2. Standardized city accuracy (%).
3. Full 3-class fresher eligibility confusion matrix & accuracy.
4. Filtered binary precision, recall, and F1 on decisive ground-truth cases.
5. Explicit count and percentage of excluded uncertain ground-truth cases.

Guarantees:
- Supports variable sample size N.
- Never assumes or claims 50 if fewer are evaluated.
- Uncertain ground-truth cases are NEVER treated as true negatives.
"""
from typing import List, Dict, Any, Optional
from collections import Counter


def evaluate_classifications(
    ground_truth_records: List[Dict[str, Any]],
    model_predictions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compute comprehensive evaluation metrics against human ground-truth.

    Args:
        ground_truth_records: List of dicts with:
            - job_id (int)
            - human_role (str)
            - human_city (Optional[str])
            - human_fresher_status (str): 'fresher_friendly', 'not_fresher_friendly', 'uncertain'
        model_predictions: List of dicts with:
            - job_id (int)
            - model_role (Optional[str])
            - model_city (Optional[str])
            - model_fresher_status (Optional[str]): 'fresher_friendly', 'not_fresher_friendly', 'uncertain'

    Returns:
        Structured evaluation report.
    """
    total_evaluated = len(ground_truth_records)
    if total_evaluated == 0:
        return {
            "sample_size": 0,
            "error": "No ground truth records provided for evaluation."
        }

    preds_by_id = {p["job_id"]: p for p in model_predictions}

    role_matches = 0
    city_matches = 0
    three_class_matches = 0

    # 3x3 Confusion Matrix: [human_label][model_label]
    possible_fresher_labels = ["fresher_friendly", "not_fresher_friendly", "uncertain"]
    confusion_3x3 = {
        h_label: {m_label: 0 for m_label in possible_fresher_labels}
        for h_label in possible_fresher_labels
    }

    # Binary metrics tracking (on subset where human label != 'uncertain')
    binary_tp = 0
    binary_fp = 0
    binary_fn = 0
    binary_tn = 0
    unresolved_decisive_count = 0
    excluded_uncertain_count = 0

    for gt in ground_truth_records:
        jid = gt["job_id"]
        pred = preds_by_id.get(jid, {})

        h_role = (gt.get("human_role") or "").strip().lower()
        m_role = (pred.get("model_role") or "").strip().lower()
        if h_role and m_role and h_role == m_role:
            role_matches += 1

        h_city = (gt.get("human_city") or "unknown").strip().lower()
        m_city = (pred.get("model_city") or "unknown").strip().lower()
        if h_city == m_city:
            city_matches += 1

        h_fresher = gt.get("human_fresher_status", "uncertain")
        m_fresher = pred.get("model_fresher_status", "uncertain")

        # 3-Class Matrix
        if h_fresher in confusion_3x3 and m_fresher in confusion_3x3[h_fresher]:
            confusion_3x3[h_fresher][m_fresher] += 1

        if h_fresher == m_fresher:
            three_class_matches += 1

        # Binary Filtered Metrics: Exclude uncertain ground-truth cases
        if h_fresher == "uncertain":
            excluded_uncertain_count += 1
        elif h_fresher == "fresher_friendly":
            if m_fresher == "fresher_friendly":
                binary_tp += 1
            else:
                binary_fn += 1
        elif h_fresher == "not_fresher_friendly":
            if m_fresher == "fresher_friendly":
                binary_fp += 1
            elif m_fresher == "not_fresher_friendly":
                binary_tn += 1
            else:
                # Model predicted 'uncertain' on a true negative case:
                # Must NOT count as True Negative; tracked as unresolved decisive case.
                unresolved_decisive_count += 1

    # Accuracies
    role_acc = round((role_matches / total_evaluated) * 100.0, 2)
    city_acc = round((city_matches / total_evaluated) * 100.0, 2)
    three_class_acc = round((three_class_matches / total_evaluated) * 100.0, 2)

    # Binary Precision, Recall, F1, FPR, FNR, Specificity on decisive ground truth cases
    decisive_total = total_evaluated - excluded_uncertain_count
    if (binary_tp + binary_fp) > 0:
        precision = round(binary_tp / (binary_tp + binary_fp), 4)
    else:
        precision = 0.0

    if (binary_tp + binary_fn) > 0:
        recall = round(binary_tp / (binary_tp + binary_fn), 4)
    else:
        recall = 0.0

    if (precision + recall) > 0:
        f1_score = round(2.0 * (precision * recall) / (precision + recall), 4)
    else:
        f1_score = 0.0

    # False Positive Rate (FPR = FP / (FP + TN))
    if (binary_fp + binary_tn) > 0:
        false_positive_rate = round(binary_fp / (binary_fp + binary_tn), 4)
    else:
        false_positive_rate = 0.0

    # False Negative Rate (FNR = FN / (FN + TP))
    if (binary_fn + binary_tp) > 0:
        false_negative_rate = round(binary_fn / (binary_fn + binary_tp), 4)
    else:
        false_negative_rate = 0.0

    # Specificity / True Negative Rate (TNR = TN / (TN + FP))
    if (binary_tn + binary_fp) > 0:
        specificity = round(binary_tn / (binary_tn + binary_fp), 4)
    else:
        specificity = 0.0

    excluded_pct = round((excluded_uncertain_count / total_evaluated) * 100.0, 2)

    return {
        "sample_size": total_evaluated,
        "decisive_sample_size": decisive_total,
        "excluded_uncertain_ground_truth_count": excluded_uncertain_count,
        "excluded_uncertain_percentage": excluded_pct,
        "role_classification_accuracy_pct": role_acc,
        "city_standardization_accuracy_pct": city_acc,
        "fresher_three_class_accuracy_pct": three_class_acc,
        "three_class_confusion_matrix": confusion_3x3,
        "binary_metrics_on_decisive_cases": {
            "true_positives": binary_tp,
            "false_positives": binary_fp,
            "false_negatives": binary_fn,
            "true_negatives": binary_tn,
            "unresolved_cases": unresolved_decisive_count,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
            "specificity": specificity
        }
    }


def print_evaluation_report(metrics: Dict[str, Any]) -> None:
    """Format and print an ASCII evaluation report."""
    print("=" * 70)
    print("GROUND-TRUTH CLASSIFICATION EVALUATION REPORT")
    print("=" * 70)
    print(f"Total Verified Sample Size Evaluated (N): {metrics['sample_size']}")
    print(f"Decisive Ground-Truth Cases:              {metrics['decisive_sample_size']}")
    print(f"Excluded Uncertain Ground-Truth Cases:    {metrics['excluded_uncertain_ground_truth_count']} ({metrics['excluded_uncertain_percentage']}%)")
    print("-" * 70)
    print("OVERALL ACCURACY METRICS:")
    print(f"  Role Classification Accuracy:           {metrics['role_classification_accuracy_pct']}%")
    print(f"  City Standardization Accuracy:          {metrics['city_standardization_accuracy_pct']}%")
    print(f"  Fresher 3-Class Accuracy:               {metrics['fresher_three_class_accuracy_pct']}%")
    print("-" * 70)
    print("BINARY FRESHER METRICS (Excluding Uncertain Cases):")
    b = metrics["binary_metrics_on_decisive_cases"]
    unres_str = f" | Unresolved: {b.get('unresolved_cases', 0)}" if 'unresolved_cases' in b else ""
    print(f"  TP: {b['true_positives']} | FP: {b['false_positives']} | FN: {b['false_negatives']} | TN: {b['true_negatives']}{unres_str}")
    print(f"  Precision:                              {b['precision']:.4f}")
    print(f"  Recall (TPR):                           {b['recall']:.4f}")
    print(f"  F1 Score:                               {b['f1_score']:.4f}")
    print(f"  False Positive Rate (FPR):              {b['false_positive_rate']:.4f}")
    print(f"  False Negative Rate (FNR):              {b['false_negative_rate']:.4f}")
    print(f"  Specificity (TNR):                      {b['specificity']:.4f}")
    print("-" * 70)
    print("3x3 FRESHER CONFUSION MATRIX (Rows=Human, Columns=Model):")
    matrix = metrics["three_class_confusion_matrix"]
    headers = ["Human \\ Model", "fresher", "not_fresher", "uncertain"]
    print(f"{headers[0]:<22} | {headers[1]:<10} | {headers[2]:<12} | {headers[3]:<10}")
    print("-" * 62)
    for h_label, row in matrix.items():
        print(f"{h_label:<22} | {row['fresher_friendly']:<10} | {row['not_fresher_friendly']:<12} | {row['uncertain']:<10}")
    print("=" * 70)
