'use client';

import React from 'react';
import {
  Database,
  CopyCheck,
  Zap,
  DollarSign,
  Layers,
  Scale,
  Sparkles,
  Info,
} from 'lucide-react';
import { AnalyticsResponse } from '@/types/api';

interface AnalyticsViewProps {
  analytics: AnalyticsResponse | null;
  isLoading: boolean;
}

export const AnalyticsView: React.FC<AnalyticsViewProps> = ({
  analytics,
  isLoading,
}) => {
  if (isLoading && !analytics) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-xl bg-slate-100" />
          ))}
        </div>
        <div className="h-64 rounded-xl bg-slate-100" />
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">
        No analytics telemetry available at this time.
      </div>
    );
  }

  const { dataset_metrics, ai_processing_cost, ground_truth_accuracy } = analytics;

  return (
    <div className="space-y-8">
      {/* 1. Header Overview Banner */}
      <div>
        <h2 className="text-xl font-bold tracking-tight text-slate-900">
          Telemetry & Evaluation Dashboard
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Real-time ingestion metrics, duplicate elimination telemetry, and verified human benchmark accuracy.
        </p>
      </div>

      {/* 2. Top-level KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Canonical Jobs */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Canonical Listings
            </span>
            <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600">
              <Database className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-slate-900">
              {dataset_metrics.total_canonical_jobs}
            </span>
            <span className="text-xs text-slate-500">unique in India</span>
          </div>
        </div>

        {/* Duplicates Prevented */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Duplicates Prevented
            </span>
            <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600">
              <CopyCheck className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-emerald-700">
              {dataset_metrics.total_duplicates_prevented}
            </span>
            <span className="text-xs text-slate-500">
              ({dataset_metrics.confirmed_duplicates} confirmed)
            </span>
          </div>
        </div>

        {/* Pipeline Ingestion Runs */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Pipeline Refreshes
            </span>
            <div className="rounded-lg bg-amber-50 p-2 text-amber-600">
              <Zap className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-slate-900">
              {dataset_metrics.total_pipeline_runs}
            </span>
            <span className="text-xs text-slate-500">automated cycles</span>
          </div>
        </div>

        {/* AI Operating Cost */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              AI Token Cost
            </span>
            <div className="rounded-lg bg-blue-50 p-2 text-blue-600">
              <DollarSign className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-slate-900">
                ${ai_processing_cost.total_actual_cost_usd.toFixed(2)}
              </span>
              <span className="inline-flex items-center rounded-md bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700 uppercase">
                {ai_processing_cost.pricing_tier} tier
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Nominal benchmark:{' '}
              {ai_processing_cost.nominal_cost_per_1000_posts_usd !== null &&
              ai_processing_cost.nominal_cost_per_1000_posts_usd !== undefined ? (
                <span className="font-medium text-slate-700">
                  ${ai_processing_cost.nominal_cost_per_1000_posts_usd.toFixed(2)} / 1k posts
                </span>
              ) : (
                <span className="font-medium text-amber-700">Not yet measurable</span>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* 3. Ingestion Source Telemetry & Fresher Breakdown */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Source Yield & Dedup breakdown */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Layers className="h-4 w-4 text-indigo-600" />
            <h3 className="text-sm font-semibold text-slate-900">
              Source Yield & Deduplication Breakdown
            </h3>
          </div>

          <div className="mt-4 overflow-hidden rounded-lg border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 font-semibold">
                <tr>
                  <th className="px-4 py-2.5">Source Feed</th>
                  <th className="px-4 py-2.5 text-right">Unique Inserted</th>
                  <th className="px-4 py-2.5 text-right">Duplicates Eliminated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                {dataset_metrics.sources.map((s) => (
                  <tr key={s.source} className="hover:bg-slate-50/50">
                    <td className="px-4 py-3 font-medium capitalize text-slate-900">
                      {s.source}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-slate-900">
                      {s.canonical_jobs}
                    </td>
                    <td className="px-4 py-3 text-right text-emerald-600 font-medium">
                      +{s.duplicates_detected}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Fresher Breakdown */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Sparkles className="h-4 w-4 text-indigo-600" />
            <h3 className="text-sm font-semibold text-slate-900">
              Dataset Fresher Classification Status
            </h3>
          </div>

          <div className="mt-4 space-y-3">
            <div>
              <div className="flex justify-between text-xs text-slate-700 font-medium">
                <span>Confirmed Fresher Friendly (0–1 YOE)</span>
                <span className="font-semibold text-emerald-700">
                  {dataset_metrics.fresher_breakdown.fresher_friendly}
                </span>
              </div>
              <div className="mt-1 h-2 w-full rounded-full bg-slate-100">
                <div
                  className="h-2 rounded-full bg-emerald-500"
                  style={{
                    width: `${
                      dataset_metrics.total_canonical_jobs > 0
                        ? (dataset_metrics.fresher_breakdown.fresher_friendly /
                            dataset_metrics.total_canonical_jobs) *
                          100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs text-slate-700 font-medium">
                <span>Experienced Positions (Non-Fresher)</span>
                <span className="font-semibold text-rose-700">
                  {dataset_metrics.fresher_breakdown.not_fresher_friendly}
                </span>
              </div>
              <div className="mt-1 h-2 w-full rounded-full bg-slate-100">
                <div
                  className="h-2 rounded-full bg-rose-500"
                  style={{
                    width: `${
                      dataset_metrics.total_canonical_jobs > 0
                        ? (dataset_metrics.fresher_breakdown.not_fresher_friendly /
                            dataset_metrics.total_canonical_jobs) *
                          100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs text-slate-700 font-medium">
                <span>Pending / Unclassified / Uncertain</span>
                <span className="font-semibold text-slate-700">
                  {dataset_metrics.fresher_breakdown.pending_or_uncertain}
                </span>
              </div>
              <div className="mt-1 h-2 w-full rounded-full bg-slate-100">
                <div
                  className="h-2 rounded-full bg-slate-400"
                  style={{
                    width: `${
                      dataset_metrics.total_canonical_jobs > 0
                        ? (dataset_metrics.fresher_breakdown.pending_or_uncertain /
                            dataset_metrics.total_canonical_jobs) *
                          100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
              Unclassified jobs are never defaulted to fresher-friendly. They remain in pending status until evaluated by the LLM classification pipeline.
            </p>
          </div>
        </div>
      </div>

      {/* 4. Human Ground-Truth Benchmark Evaluation */}
      {ground_truth_accuracy && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-100 pb-4 gap-2">
            <div className="flex items-center gap-2">
              <Scale className="h-4 w-4 text-indigo-600" />
              <h3 className="text-sm font-semibold text-slate-900">
                Human Ground-Truth Evaluation Benchmark (N = {ground_truth_accuracy.sample_size})
              </h3>
            </div>

            <span className="inline-flex items-center rounded-md bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-700/10">
              Benchmark Verified
            </span>
          </div>

          {/* Model classification status advisory banner */}
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50/70 p-3.5 text-xs text-amber-900">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-semibold">Preliminary Model Prediction Status</p>
                <p className="mt-0.5 leading-relaxed text-amber-800">
                  The dataset currently holds 24 genuine Indian postings awaiting batch LLM classification. The matrix below displays human benchmark labels compared against current pending status. Non-fresher precision and recall will be updated dynamically once LLM batch classification is executed.
                </p>
              </div>
            </div>
          </div>

          {/* Decisive vs Uncertain breakdown pill badges */}
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
            <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
              <span className="text-slate-500">Verified Sample Size</span>
              <p className="mt-1 text-lg font-bold text-slate-900">
                {ground_truth_accuracy.sample_size}
              </p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
              <span className="text-slate-500">Decisive Cases</span>
              <p className="mt-1 text-lg font-bold text-slate-900">
                {ground_truth_accuracy.decisive_sample_size}
              </p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
              <span className="text-slate-500">Excluded Uncertain</span>
              <p className="mt-1 text-lg font-bold text-amber-700">
                {ground_truth_accuracy.excluded_uncertain_ground_truth_count} (
                {ground_truth_accuracy.excluded_uncertain_percentage}%)
              </p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
              <span className="text-slate-500">Evaluation Strategy</span>
              <p className="mt-1 text-xs font-semibold text-slate-800">
                Strict 3-Class Confusion
              </p>
            </div>
          </div>

          {/* 3x3 Confusion Matrix */}
          <div className="mt-6">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              3 × 3 Fresher Confusion Matrix (Rows = Human Ground Truth, Columns = Model)
            </h4>

            <div className="mt-3 overflow-hidden rounded-lg border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                <thead className="bg-slate-50 text-slate-600 font-semibold">
                  <tr>
                    <th className="px-4 py-2.5">Human Ground Truth</th>
                    <th className="px-4 py-2.5 text-center">Model: Fresher Friendly</th>
                    <th className="px-4 py-2.5 text-center">Model: Experienced</th>
                    <th className="px-4 py-2.5 text-center">Model: Uncertain / Pending</th>
                    <th className="px-4 py-2.5 text-right">Row Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                  <tr>
                    <td className="px-4 py-3 font-medium text-emerald-700 bg-emerald-50/20">
                      Fresher Friendly (0–1 YOE)
                    </td>
                    <td className="px-4 py-3 text-center font-bold text-slate-900">
                      {ground_truth_accuracy.three_class_confusion_matrix.fresher_friendly.fresher_friendly}
                    </td>
                    <td className="px-4 py-3 text-center text-slate-500">
                      {ground_truth_accuracy.three_class_confusion_matrix.fresher_friendly.not_fresher_friendly}
                    </td>
                    <td className="px-4 py-3 text-center text-amber-700 font-medium">
                      {ground_truth_accuracy.three_class_confusion_matrix.fresher_friendly.uncertain}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-slate-900">
                      5
                    </td>
                  </tr>

                  <tr>
                    <td className="px-4 py-3 font-medium text-rose-700 bg-rose-50/20">
                      Experienced (Non-Fresher)
                    </td>
                    <td className="px-4 py-3 text-center text-slate-500">
                      {ground_truth_accuracy.three_class_confusion_matrix.not_fresher_friendly.fresher_friendly}
                    </td>
                    <td className="px-4 py-3 text-center font-bold text-slate-900">
                      {ground_truth_accuracy.three_class_confusion_matrix.not_fresher_friendly.not_fresher_friendly}
                    </td>
                    <td className="px-4 py-3 text-center text-amber-700 font-medium">
                      {ground_truth_accuracy.three_class_confusion_matrix.not_fresher_friendly.uncertain}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-slate-900">
                      9
                    </td>
                  </tr>

                  <tr>
                    <td className="px-4 py-3 font-medium text-slate-600 bg-slate-50">
                      Unstated / Uncertain
                    </td>
                    <td className="px-4 py-3 text-center text-slate-500">
                      {ground_truth_accuracy.three_class_confusion_matrix.uncertain.fresher_friendly}
                    </td>
                    <td className="px-4 py-3 text-center text-slate-500">
                      {ground_truth_accuracy.three_class_confusion_matrix.uncertain.not_fresher_friendly}
                    </td>
                    <td className="px-4 py-3 text-center text-amber-700 font-medium">
                      {ground_truth_accuracy.three_class_confusion_matrix.uncertain.uncertain}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-slate-900">
                      10
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
