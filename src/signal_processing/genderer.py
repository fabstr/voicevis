import logging

import numpy as np
from scipy.spatial.distance import mahalanobis
from scipy.stats import multivariate_normal
from signal_processing.AudioFeatures import SignalTimeSeries
from ResourceManager import ResourceManager
from signal_processing.TargetConfig import TargetConfig


def estimate_target_distribution(target_config: TargetConfig):
    """
    Converts a TargetConfig object into a mean vector and a covariance matrix.
    Assumes features are independent (diagonal covariance matrix).
    """
    means = []
    variances = []

    # Iterate over the exact required features for our Mahalanobis space
    for feature in ['pitch', 'size', 'weight']:
        bounds = target_config.get_bounds(feature)

        if bounds is None:
            raise ValueError(f"Feature '{feature}' is missing from target config '{target_config.config_name}'")

        f_min, f_max, enabled = bounds

        # Mean is the midpoint
        mean = (f_min + f_max) / 2.0
        # Assume max - min covers 4 standard deviations (95% of data)
        std_dev = (f_max - f_min) / 4.0
        # Prevent division by zero if min == max
        variance = max(std_dev ** 2, 1e-6)

        means.append(mean)
        variances.append(variance)

    mean_vector = np.array(means)
    covariance_matrix = np.diag(variances)  # Diagonal matrix assuming independence

    return mean_vector, covariance_matrix


def evaluate_probabilities(pitch_ts, size_ts, weight_ts, targets_configs):
    # 1. Extract the latest observation vector
    # (Using get_last_y() as per your dataclass, assuming last point is the current state)
    observation = np.array([
        pitch_ts.get_last_y(),
        size_ts.get_last_y(),
        weight_ts.get_last_y()
    ])

    if np.any(np.isnan(observation)):
        raise ValueError("Current observation contains NaN values. Cannot calculate distance.")

    results = {}
    likelihoods = []
    target_names = list(targets_configs.keys())

    # 2. Calculate Mahalanobis Distance and Likelihood for each target
    for name, config in targets_configs.items():
        mean_vec, cov_matrix = estimate_target_distribution(config)
        inv_cov_matrix = np.linalg.inv(cov_matrix)

        # Calculate Mahalanobis Distance
        mahal_dist = mahalanobis(observation, mean_vec, inv_cov_matrix)

        # Calculate Gaussian Likelihood (probability density)
        # multivariate_normal handles the core Mahalanobis math under the hood
        likelihood = multivariate_normal.pdf(observation, mean=mean_vec, cov=cov_matrix)

        likelihoods.append(likelihood)
        results[name] = {
            "mahalanobis_distance": mahal_dist,
            "likelihood": likelihood
        }

    # 3. Normalize likelihoods to get relative probabilities (Bayesian approach with uniform prior)
    total_likelihood = sum(likelihoods)

    if total_likelihood == 0:
        # Avoid division by zero if observation is infinitely far from all targets
        probabilities = [1.0 / len(target_names)] * len(target_names)
    else:
        probabilities = [lk / total_likelihood for lk in likelihoods]

    for i, name in enumerate(target_names):
        results[name]["probability"] = probabilities[i]

    # 4. Determine the most probable target
    most_probable_target = max(results, key=lambda k: results[k]["probability"])

    return results, most_probable_target

def calculate_target_probabilities(pitch: SignalTimeSeries, size: SignalTimeSeries, weight: SignalTimeSeries):
    rm = ResourceManager()
    targets = {}
    for file in rm.get_matching_files(".*.json", "targets"):
        target = TargetConfig.from_json(file)
        targets[target.config_name] = target

    valid_mask = ~(np.isnan(pitch.y) | np.isnan(size.y) | np.isnan(weight.y))
    if not np.any(valid_mask):
        logging.warning("Warning: No concurrent valid data points found across all series.")
        return {}  # Or handle this edge-case as required by your application

    clean_pitch = SignalTimeSeries(x=pitch.x[valid_mask], y=pitch.y[valid_mask])
    clean_size = SignalTimeSeries(x=size.x[valid_mask], y=size.y[valid_mask])
    clean_weight = SignalTimeSeries(x=weight.x[valid_mask], y=weight.y[valid_mask])

    metrics, best_match = evaluate_probabilities(clean_pitch, clean_size, clean_weight, targets)
    results = {}
    for target, data in metrics.items():
        results[target] = round(100*data['probability']) # convert to integer percent

    return results

# ==========================================
# EXAMPLE USAGE
# ==========================================
if __name__ == "__main__":
    # Mocking current time series data (the latest point is what we will test)
    pitch_series = SignalTimeSeries(y=np.array([10.0, 12.0, 14.5]))
    size_series = SignalTimeSeries(y=np.array([100.0, 102.0, 105.0]))
    weight_series = SignalTimeSeries(y=np.array([50.0, 52.0, 55.0]))

    # Define the static target profiles with min/max values
    targets_definition = {
        "Target_A": {
            "pitch": {"min": 10.0, "max": 20.0},
            "size": {"min": 90.0, "max": 110.0},
            "weight": {"min": 40.0, "max": 60.0}
        },
        "Target_B": {
            "pitch": {"min": 0.0, "max": 8.0},
            "size": {"min": 50.0, "max": 70.0},
            "weight": {"min": 10.0, "max": 30.0}
        },
        "Target_C": {
            "pitch": {"min": 13.0, "max": 17.0},
            "size": {"min": 103.0, "max": 107.0},
            "weight": {"min": 53.0, "max": 57.0}
        }
    }

    # Run evaluation
    metrics, best_match = evaluate_probabilities(pitch_series, size_series, weight_series, targets_definition)

    print(str(calculate_target_probabilities(pitch_series, size_series, weight_series, targets_definition)))
    #
    # print(f"--- Evaluation Results ---")
    # print(f"Most Probable Target: {best_match}\n")
    # for target, data in metrics.items():
    #     print(f"[{target}]:")
    #     print(f"  - Mahalanobis Distance: {data['mahalanobis_distance']:.4f}")
    #     print(f"  - Probability:         {data['probability'] * 100:.2f}%")