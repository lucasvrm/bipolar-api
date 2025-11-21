// k6 load test for predictions endpoint
// Usage: k6 run load_tests/predictions_load_test.js
//
// Environment variables:
//   - BASE_URL: API base URL (default: http://localhost:8000)
//   - VUS: Number of virtual users (default: 10)
//   - DURATION: Test duration (default: 30s)

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const cacheHitRate = new Rate('cache_hits');
const requestDuration = new Trend('request_duration');

// Test configuration
export const options = {
  stages: [
    { duration: '10s', target: __ENV.VUS || 5 },   // Ramp up
    { duration: __ENV.DURATION || '30s', target: __ENV.VUS || 10 }, // Sustained load
    { duration: '10s', target: 0 },                // Ramp down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<1000'], // 95% of requests should complete in < 1s
    'http_req_failed': ['rate<0.1'],     // Error rate should be < 10%
    'errors': ['rate<0.1'],               // Custom error rate < 10%
  },
};

// Sample user IDs for testing
const TEST_USER_IDS = [
  '123e4567-e89b-12d3-a456-426614174000',
  '223e4567-e89b-12d3-a456-426614174001',
  '323e4567-e89b-12d3-a456-426614174002',
  '423e4567-e89b-12d3-a456-426614174003',
  '523e4567-e89b-12d3-a456-426614174004',
];

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  // Select a random user
  const userId = TEST_USER_IDS[Math.floor(Math.random() * TEST_USER_IDS.length)];
  
  // Test 1: Get all predictions (default)
  const startTime = Date.now();
  const response = http.get(`${BASE_URL}/data/predictions/${userId}`);
  const duration = Date.now() - startTime;
  
  requestDuration.add(duration);
  
  // Check response
  const success = check(response, {
    'status is 200': (r) => r.status === 200,
    'has predictions': (r) => {
      const body = JSON.parse(r.body);
      return body.predictions && Array.isArray(body.predictions);
    },
    'predictions count is 5': (r) => {
      const body = JSON.parse(r.body);
      return body.predictions.length === 5;
    },
    'response time < 1000ms': () => duration < 1000,
    'response time < 500ms (ideal)': () => duration < 500,
  });
  
  errorRate.add(!success);
  
  // Detect cache hit (subsequent requests should be faster)
  if (response.status === 200) {
    const body = JSON.parse(response.body);
    // Assume cache hit if response time is very fast
    cacheHitRate.add(duration < 100);
  }
  
  // Test 2: Get specific prediction types
  if (Math.random() > 0.5) {
    http.get(`${BASE_URL}/data/predictions/${userId}?types=mood_state,relapse_risk`);
  }
  
  // Test 3: Different window_days
  if (Math.random() > 0.7) {
    http.get(`${BASE_URL}/data/predictions/${userId}?window_days=7`);
  }
  
  // Sleep to simulate user think time
  sleep(Math.random() * 2 + 1); // 1-3 seconds
}

// Setup function (runs once)
export function setup() {
  console.log(`Starting load test against ${BASE_URL}`);
  console.log(`VUs: ${__ENV.VUS || 10}, Duration: ${__ENV.DURATION || '30s'}`);
  
  // Health check
  const health = http.get(`${BASE_URL}/`);
  check(health, {
    'API is healthy': (r) => r.status === 200,
  });
  
  return { baseUrl: BASE_URL };
}

// Teardown function (runs once)
export function teardown(data) {
  console.log('Load test completed');
}
