'use client';

import React from 'react';
import {
  Building2,
  MapPin,
  ExternalLink,
  Calendar,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Layers,
} from 'lucide-react';
import { Job } from '../types/api';

interface JobCardProps {
  job: Job;
}

export const JobCard: React.FC<JobCardProps> = ({ job }) => {
  // Format posted date
  const formattedDate = job.posted_at
    ? new Date(job.posted_at).toLocaleDateString('en-IN', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

  // Determine fresher badge styling and text
  const renderFresherBadge = () => {
    if (job.is_fresher_friendly === true || job.fresher_eligibility_status === 'fresher_friendly') {
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
          <span>Fresher Friendly (0–1 YOE)</span>
        </span>
      );
    }

    if (job.is_fresher_friendly === false || job.fresher_eligibility_status === 'not_fresher_friendly') {
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-1 text-xs font-semibold text-rose-700 ring-1 ring-inset ring-rose-600/20">
          <AlertCircle className="h-3.5 w-3.5 text-rose-600" />
          <span>Experienced Position</span>
        </span>
      );
    }

    if (job.fresher_eligibility_status === 'uncertain') {
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-purple-50 px-2 py-1 text-xs font-medium text-purple-700 ring-1 ring-inset ring-purple-600/20">
          <HelpCircle className="h-3.5 w-3.5 text-purple-500" />
          <span>Model Result: Uncertain</span>
        </span>
      );
    }

    // Pending / Unclassified (fresher_eligibility_status is null/undefined)
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-500/10">
        <HelpCircle className="h-3.5 w-3.5 text-slate-400" />
        <span>Pending AI Verification</span>
      </span>
    );
  };

  // Location display logic
  const displayLocation = job.standardized_city || job.raw_location || 'Location Unspecified';

  return (
    <article className="group relative flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-300 hover:shadow-md">
      <div>
        {/* Header: Badges & Source */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div className="flex flex-wrap items-center gap-2">
            {renderFresherBadge()}

            {job.role_category && (
              <span className="inline-flex items-center rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-700/10">
                {job.role_category}
              </span>
            )}

            {job.job_type && (
              <span className="inline-flex items-center rounded-md bg-slate-50 px-2 py-1 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-500/10">
                {job.job_type}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Layers className="h-3.5 w-3.5" />
            <span className="capitalize">{job.source}</span>
          </div>
        </div>

        {/* Job Title & Company */}
        <div className="mt-3.5">
          <h3 className="text-base font-semibold text-slate-900 group-hover:text-indigo-600 transition">
            {job.title}
          </h3>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
            <div className="flex items-center gap-1.5">
              <Building2 className="h-4 w-4 text-slate-400 flex-shrink-0" />
              <span className="font-medium text-slate-800">
                {job.company || 'Confidential / Unspecified'}
              </span>
            </div>

            <div className="flex items-center gap-1.5 text-slate-500">
              <MapPin className="h-4 w-4 text-slate-400 flex-shrink-0" />
              <span>{displayLocation}</span>
            </div>
          </div>
        </div>

        {/* Job Description Snippet */}
        {job.description && (
          <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-slate-500">
            {job.description}
          </p>
        )}
      </div>

      {/* Footer: Date & Direct Apply Action */}
      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-3.5">
        <div className="flex items-center gap-1 text-xs text-slate-400">
          <Calendar className="h-3.5 w-3.5" />
          <span>{formattedDate ? `Posted ${formattedDate}` : 'Recently scraped'}</span>
        </div>

        <a
          href={job.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 transition"
        >
          <span>Apply Direct</span>
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>
    </article>
  );
};
