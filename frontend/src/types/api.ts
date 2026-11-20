/**
 * Data contracts and response schemas for Beep Job Aggregator API.
 */

export interface Job {
  id: number;
  source: string;
  external_id: string;
  title: string;
  company?: string | null;
  raw_location?: string | null;
  standardized_city?: string | null;
  description?: string | null;
  apply_url: string;
  canonical_url_hash: string;
  content_hash: string;
  role_category?: string | null;
  job_type?: string | null;
  fresher_eligibility_status?: 'fresher_friendly' | 'not_fresher_friendly' | 'uncertain' | null;
  is_fresher_friendly?: boolean | null;
  model_confidence?: number | null;
  classification_error?: string | null;
  posted_at?: string | null;
  created_at: string;
  is_active: boolean;
}

export interface JobListResponse {
  total: number;
  page: number;
  limit: number;
  pages: number;
  jobs: Job[];
}

export interface FacetCount {
  name: string;
  count: number;
}

export interface FilterFacets {
  total_jobs: number;
  fresher_friendly_count: number;
  roles: FacetCount[];
  cities: FacetCount[];
  job_types: FacetCount[];
  sources: FacetCount[];
}

export interface FresherBreakdown {
  fresher_friendly: number;
  not_fresher_friendly: number;
  pending_or_uncertain: number;
}

export interface SourceBreakdown {
  source: string;
  canonical_jobs: number;
  duplicates_detected: number;
}

export interface DatasetMetrics {
  total_canonical_jobs: number;
  total_duplicates_prevented: number;
  confirmed_duplicates: number;
  potential_duplicates: number;
  total_pipeline_runs: number;
  fresher_breakdown: FresherBreakdown;
  sources: SourceBreakdown[];
}

export interface AIProcessingCost {
  total_batches: number;
  total_jobs_processed: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_actual_cost_usd: number;
  total_nominal_cost_usd: number;
  nominal_cost_per_1000_posts_usd: number | null;
  pricing_tier: string;
}

export interface BinaryMetrics {
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  true_negatives: number;
  precision: number;
  recall: number;
  f1_score: number;
}

export interface ThreeClassConfusionMatrix {
  fresher_friendly: {
    fresher_friendly: number;
    not_fresher_friendly: number;
    uncertain: number;
  };
  not_fresher_friendly: {
    fresher_friendly: number;
    not_fresher_friendly: number;
    uncertain: number;
  };
  uncertain: {
    fresher_friendly: number;
    not_fresher_friendly: number;
    uncertain: number;
  };
}

export interface GroundTruthAccuracyReport {
  sample_size: number;
  decisive_sample_size: number;
  excluded_uncertain_ground_truth_count: number;
  excluded_uncertain_percentage: number;
  role_classification_accuracy_pct: number;
  city_standardization_accuracy_pct: number;
  fresher_three_class_accuracy_pct: number;
  three_class_confusion_matrix: ThreeClassConfusionMatrix;
  binary_metrics_on_decisive_cases: BinaryMetrics;
}

export interface AnalyticsResponse {
  dataset_metrics: DatasetMetrics;
  ai_processing_cost: AIProcessingCost;
  ground_truth_accuracy?: GroundTruthAccuracyReport | null;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  database: string;
  environment: string;
  pricing_tier: string;
}

export interface JobFilterParams {
  q?: string;
  role?: string[];
  city?: string[];
  job_type?: string[];
  fresher_only?: boolean;
  fresher_status?: 'fresher_friendly' | 'not_fresher_friendly' | 'uncertain' | 'pending' | 'unstated';
  source?: string[];
  page?: number;
  limit?: number;
  sort_by?: 'recent' | 'title' | 'company';
}
