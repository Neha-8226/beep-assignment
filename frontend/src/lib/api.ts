/**
 * API client layer communicating with FastAPI backend.
 * Handles query parameter serialization, type-checking, and error recovery.
 */

import {
  JobListResponse,
  FilterFacets,
  Job,
  AnalyticsResponse,
  HealthResponse,
  JobFilterParams,
} from '@/types/api';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options?.headers || {}),
      },
      cache: 'no-store', // Always fetch fresh data for dynamic filters & health
    });

    if (!res.ok) {
      let errorDetail = `Request failed with status ${res.status}`;
      try {
        const errorJson = await res.json();
        if (errorJson.detail) {
          errorDetail = typeof errorJson.detail === 'string'
            ? errorJson.detail
            : JSON.stringify(errorJson.detail);
        }
      } catch {
        // Fall back to status text
      }
      throw new ApiError(errorDetail, res.status);
    }

    return (await res.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      error instanceof Error ? error.message : 'Network error or backend unreachable',
      0
    );
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export async function fetchJobs(params: JobFilterParams = {}): Promise<JobListResponse> {
  const query = new URLSearchParams();

  if (params.q && params.q.trim()) {
    query.set('q', params.q.trim());
  }

  if (params.role && params.role.length > 0) {
    query.set('role', params.role.join(','));
  }

  if (params.city && params.city.length > 0) {
    query.set('city', params.city.join(','));
  }

  if (params.job_type && params.job_type.length > 0) {
    query.set('job_type', params.job_type.join(','));
  }

  if (params.source && params.source.length > 0) {
    query.set('source', params.source.join(','));
  }

  if (params.fresher_only) {
    query.set('fresher_only', 'true');
  } else if (params.fresher_status) {
    query.set('fresher_status', params.fresher_status);
  }

  if (params.page && params.page > 0) {
    query.set('page', params.page.toString());
  }

  if (params.limit && params.limit > 0) {
    query.set('limit', params.limit.toString());
  }

  if (params.sort_by) {
    query.set('sort_by', params.sort_by);
  }

  const qs = query.toString();
  const endpoint = `/jobs${qs ? `?${qs}` : ''}`;
  return request<JobListResponse>(endpoint);
}

export async function fetchJobFilters(): Promise<FilterFacets> {
  return request<FilterFacets>('/jobs/filters');
}

export async function fetchJobById(id: number): Promise<Job> {
  return request<Job>(`/jobs/${id}`);
}

export async function fetchAnalytics(): Promise<AnalyticsResponse> {
  return request<AnalyticsResponse>('/analytics');
}
