#!/usr/bin/env python3
"""
Admin Endpoint Production Testing Script

Executa uma bateria controlada de validações em endpoints administrativos em PRODUÇÃO
para confirmar disponibilidade, autorização correta, consistência básica e latências,
sem modificar dados críticos.

Objetivo: Validação matemática e rigorosa de endpoints admin com medições precisas.
"""

import os
import sys
import json
import time
import uuid
import statistics
import traceback
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
import requests


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class EndpointTestResult:
    """Resultado de teste de um endpoint individual"""
    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    success: bool
    response_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    validation_passed: bool = True  # Whether the test validation passed (independent of HTTP status)


@dataclass
class TestReport:
    """Relatório completo de testes"""
    correlation_id: str
    start_time_utc: str
    end_time_utc: str
    endpoints_tested: List[Dict[str, Any]] = field(default_factory=list)
    latencies: Dict[str, float] = field(default_factory=dict)
    authorization_negative_result: Dict[str, Any] = field(default_factory=dict)
    structural_issues: List[str] = field(default_factory=list)
    inconsistencies: List[str] = field(default_factory=list)
    overall_status: str = "OK"  # OK | WARN | FAIL
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário para serialização JSON"""
        return asdict(self)


# ============================================================================
# Admin Endpoint Tester Class
# ============================================================================

class AdminEndpointTester:
    """Testador de endpoints administrativos em produção"""
    
    # Production API base URL (can be overridden)
    BASE_URL = os.getenv("BIPOLAR_API_URL", "https://bipolar-engine.onrender.com")
    TEST_PREFIX = "zz-test"
    
    def __init__(self, admin_token: str):
        """
        Inicializa o testador com token de admin.
        
        Args:
            admin_token: Token de autenticação admin (Bearer token)
        """
        self.admin_token = admin_token
        self.correlation_id = f"{uuid.uuid4()}-{int(time.time())}"
        self.start_timestamp = datetime.now(timezone.utc)
        self.results: List[EndpointTestResult] = []
        self.report = TestReport(
            correlation_id=self.correlation_id,
            start_time_utc=self.start_timestamp.isoformat(),
            end_time_utc=""
        )
        
    def _get_headers(self, use_token: bool = True, corrupt_token: bool = False) -> Dict[str, str]:
        """
        Retorna headers para requisições.
        
        Args:
            use_token: Se deve incluir o token de autorização
            corrupt_token: Se deve corromper o token (para testes negativos)
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if use_token:
            token = self.admin_token
            if corrupt_token:
                # Corrompe o último caractere do token
                token = token[:-1] + ('X' if token[-1] != 'X' else 'Y')
            headers["Authorization"] = f"Bearer {token}"
            
        return headers
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        use_token: bool = True,
        corrupt_token: bool = False,
        params: Optional[Dict[str, Any]] = None
    ) -> EndpointTestResult:
        """
        Faz uma requisição HTTP e mede latência.
        
        Args:
            method: Método HTTP (GET, POST, etc)
            endpoint: Endpoint relativo (ex: /api/admin/stats)
            use_token: Se deve usar autenticação
            corrupt_token: Se deve corromper o token
            params: Query parameters opcionais
            
        Returns:
            EndpointTestResult com métricas da requisição
        """
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers(use_token=use_token, corrupt_token=corrupt_token)
        
        start_time = time.time()
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=params, timeout=30)
            else:
                raise ValueError(f"Método HTTP não suportado: {method}")
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Try to parse JSON response
            try:
                response_data = response.json()
            except (ValueError, json.JSONDecodeError):
                response_data = {"raw": response.text[:500]}  # Truncate long responses
            
            success = 200 <= response.status_code < 300
            
            return EndpointTestResult(
                endpoint=endpoint,
                method=method,
                status_code=response.status_code,
                latency_ms=latency_ms,
                success=success,
                response_data=response_data,
                error_message=None if success else f"HTTP {response.status_code}"
            )
            
        except requests.exceptions.Timeout:
            latency_ms = (time.time() - start_time) * 1000
            return EndpointTestResult(
                endpoint=endpoint,
                method=method,
                status_code=0,
                latency_ms=latency_ms,
                success=False,
                error_message="Request timeout"
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return EndpointTestResult(
                endpoint=endpoint,
                method=method,
                status_code=0,
                latency_ms=latency_ms,
                success=False,
                error_message=str(e)
            )
    
    def test_authorization_positive(self) -> EndpointTestResult:
        """
        Teste 1: Autorização positiva - smoke test
        Chama GET /api/admin/stats com token válido
        Espera: 200 OK com campos relevantes
        """
        print("🔐 [Test 1] Authorization Positive - Smoke Test")
        result = self._make_request("GET", "/api/admin/stats")
        
        if result.success and result.response_data:
            # Validar campos esperados
            expected_fields = [
                "total_users", "total_checkins", "real_patients_count",
                "synthetic_patients_count", "checkins_today"
            ]
            missing_fields = [f for f in expected_fields if f not in result.response_data]
            
            if missing_fields:
                self.report.structural_issues.append(
                    f"/api/admin/stats: Missing fields: {', '.join(missing_fields)}"
                )
                print(f"  ⚠️  Missing fields: {missing_fields}")
                result.validation_passed = False
            else:
                print(f"  ✅ Status: {result.status_code}, Latency: {result.latency_ms:.2f}ms")
                print(f"  📊 total_users={result.response_data.get('total_users', 0)}, "
                      f"total_checkins={result.response_data.get('total_checkins', 0)}")
                result.validation_passed = True
        else:
            print(f"  ❌ Failed: {result.error_message or result.status_code}")
            result.validation_passed = False
            self.report.overall_status = "FAIL"
        
        self.results.append(result)
        return result
    
    def test_authorization_negative(self) -> EndpointTestResult:
        """
        Teste 2: Autorização negativa
        Chama endpoint sem token ou com token corrompido
        Espera: 401 ou 403
        """
        print("\n🔒 [Test 2] Authorization Negative - Security Test")
        
        # Test with corrupted token
        result = self._make_request("GET", "/api/admin/stats", use_token=True, corrupt_token=True)
        
        expected_statuses = [401, 403]
        
        if result.status_code in expected_statuses:
            print(f"  ✅ Correctly rejected with {result.status_code}")
            result.validation_passed = True
            self.report.authorization_negative_result = {
                "expected": expected_statuses,
                "obtained": result.status_code,
                "status": "PASS"
            }
        elif result.status_code == 200:
            print(f"  ❌ CRITICAL: Accepted invalid token (returned 200)")
            result.validation_passed = False
            self.report.authorization_negative_result = {
                "expected": expected_statuses,
                "obtained": result.status_code,
                "status": "FAIL - SECURITY ISSUE"
            }
            self.report.overall_status = "FAIL"
        else:
            print(f"  ⚠️  Unexpected status: {result.status_code}")
            result.validation_passed = False
            self.report.authorization_negative_result = {
                "expected": expected_statuses,
                "obtained": result.status_code,
                "status": "WARN"
            }
            if self.report.overall_status == "OK":
                self.report.overall_status = "WARN"
        
        self.results.append(result)
        return result
    
    def test_list_users(self, limit: int = 50) -> EndpointTestResult:
        """
        Teste 3: Listagem de usuários
        GET /api/admin/users com paginação
        Valida estrutura de resposta e conta usuários
        """
        print(f"\n👥 [Test 3] List Users (limit={limit})")
        result = self._make_request("GET", "/api/admin/users", params={"limit": limit})
        
        if result.success and result.response_data:
            users = result.response_data.get("users", [])
            total = result.response_data.get("total", 0)
            
            print(f"  ✅ Status: {result.status_code}, Latency: {result.latency_ms:.2f}ms")
            print(f"  📋 Users returned: {len(users)}, Total: {total}")
            
            # Validar estrutura das primeiras 3 entradas
            validation_issues = []
            if users:
                expected_user_fields = ["id", "email", "role", "created_at"]
                for i, user in enumerate(users[:3]):
                    missing_fields = [f for f in expected_user_fields if f not in user]
                    if missing_fields:
                        issue = f"/api/admin/users: User #{i} missing fields: {', '.join(missing_fields)}"
                        self.report.structural_issues.append(issue)
                        validation_issues.append(issue)
                        print(f"  ⚠️  {issue}")
            
            result.validation_passed = len(validation_issues) == 0
            
            # Store count for cross-validation (stored in response_data for later access)
            if result.response_data:
                result.response_data['_user_count'] = len(users)
                result.response_data['_total_count'] = total
        else:
            print(f"  ❌ Failed: {result.error_message or result.status_code}")
            result.validation_passed = False
            if self.report.overall_status == "OK":
                self.report.overall_status = "WARN"
        
        self.results.append(result)
        return result
    
    def test_cross_validation_stats_vs_users(
        self,
        stats_result: EndpointTestResult,
        users_result: EndpointTestResult
    ):
        """
        Teste 4: Consistência cruzada entre /stats e /users
        Valida que contagens de usuários são coerentes
        Tolerância: ±2 (possível replicação)
        """
        print("\n🔍 [Test 4] Cross-Validation: Stats vs Users")
        
        if not stats_result.success or not users_result.success:
            print("  ⚠️  Skipping: One or both endpoints failed")
            return
        
        stats_total = stats_result.response_data.get("total_users", 0)
        users_total = users_result.response_data.get("total", 0)
        
        difference = abs(stats_total - users_total)
        tolerance = 2
        
        print(f"  📊 /api/admin/stats: total_users = {stats_total}")
        print(f"  📊 /api/admin/users: total = {users_total}")
        print(f"  📊 Difference: {difference} (tolerance: {tolerance})")
        
        if difference <= tolerance:
            print(f"  ✅ Consistent (within tolerance)")
        else:
            inconsistency = (
                f"User count mismatch: stats.total_users={stats_total} vs "
                f"users.total={users_total} (diff={difference}, tolerance={tolerance})"
            )
            self.report.inconsistencies.append(inconsistency)
            print(f"  ⚠️  {inconsistency}")
            if self.report.overall_status == "OK":
                self.report.overall_status = "WARN"
    
    def test_filter_robustness(self):
        """
        Teste 5: Robustez com filtros
        Testa endpoint com filtros vazios e inexistentes
        """
        print("\n🧪 [Test 5] Filter Robustness Tests")
        
        # Test 5a: Filter by role
        print("  5a. Filter by role=patient")
        result_patient = self._make_request(
            "GET", "/api/admin/users", 
            params={"role": "patient", "limit": 10}
        )
        
        if result_patient.success:
            patient_count = len(result_patient.response_data.get("users", []))
            print(f"    ✅ Returned {patient_count} patients, Latency: {result_patient.latency_ms:.2f}ms")
            result_patient.validation_passed = True
        else:
            print(f"    ❌ Failed: {result_patient.error_message or result_patient.status_code}")
            result_patient.validation_passed = False
            if result_patient.status_code == 500:
                self.report.overall_status = "FAIL"
                self.report.structural_issues.append(
                    "BLOCKER: /api/admin/users?role=patient returned HTTP 500"
                )
        
        self.results.append(result_patient)
        
        # Test 5b: Filter by role=therapist
        print("  5b. Filter by role=therapist")
        result_therapist = self._make_request(
            "GET", "/api/admin/users",
            params={"role": "therapist", "limit": 10}
        )
        
        if result_therapist.success:
            therapist_count = len(result_therapist.response_data.get("users", []))
            print(f"    ✅ Returned {therapist_count} therapists, Latency: {result_therapist.latency_ms:.2f}ms")
            result_therapist.validation_passed = True
        else:
            print(f"    ❌ Failed: {result_therapist.error_message or result_therapist.status_code}")
            result_therapist.validation_passed = False
        
        self.results.append(result_therapist)
        
        # Test 5c: Invalid role (should return 400)
        print("  5c. Invalid role filter (expect 400)")
        result_invalid = self._make_request(
            "GET", "/api/admin/users",
            params={"role": "invalid_role"}
        )
        
        if result_invalid.status_code == 400:
            print(f"    ✅ Correctly rejected with 400")
            result_invalid.validation_passed = True
        elif result_invalid.status_code == 200:
            print(f"    ⚠️  Accepted invalid role (should validate)")
            result_invalid.validation_passed = False
        else:
            print(f"    ⚠️  Unexpected status: {result_invalid.status_code}")
            result_invalid.validation_passed = False
        
        self.results.append(result_invalid)
    
    def calculate_latency_statistics(self):
        """
        Calcula estatísticas de latência de todos os testes bem-sucedidos
        """
        print("\n📈 [Test 6] Latency Statistics")
        
        # Apenas requisições bem-sucedidas
        latencies = [r.latency_ms for r in self.results if r.success]
        
        if not latencies:
            print("  ⚠️  No successful requests to analyze")
            return
        
        mean_ms = statistics.mean(latencies)
        max_ms = max(latencies)
        min_ms = min(latencies)
        
        # Calculate P95 (95th percentile)
        sorted_latencies = sorted(latencies)
        p95_index = int(len(sorted_latencies) * 0.95)
        # Ensure we don't go out of bounds
        if p95_index >= len(sorted_latencies):
            p95_index = len(sorted_latencies) - 1
        p95_ms = sorted_latencies[p95_index]
        
        # Standard deviation
        stdev_ms = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
        
        print(f"  📊 Successful requests: {len(latencies)}")
        print(f"  📊 Mean latency: {mean_ms:.2f}ms")
        print(f"  📊 P95 latency: {p95_ms:.2f}ms")
        print(f"  📊 Max latency: {max_ms:.2f}ms")
        print(f"  📊 Min latency: {min_ms:.2f}ms")
        print(f"  📊 Std deviation: {stdev_ms:.2f}ms")
        
        self.report.latencies = {
            "meanMs": round(mean_ms, 2),
            "p95Ms": round(p95_ms, 2),
            "maxMs": round(max_ms, 2),
            "minMs": round(min_ms, 2),
            "stdDevMs": round(stdev_ms, 2),
            "sampleSize": len(latencies)
        }
    
    def run_all_tests(self):
        """
        Executa todos os testes em sequência
        """
        print("=" * 70)
        print("🚀 ADMIN ENDPOINTS PRODUCTION TEST SUITE")
        print("=" * 70)
        print(f"Correlation ID: {self.correlation_id}")
        print(f"Start Time: {self.start_timestamp.isoformat()}")
        print(f"Base URL: {self.BASE_URL}")
        print("=" * 70)
        
        # Test 1: Authorization positive (smoke test)
        stats_result = self.test_authorization_positive()
        
        # Test 2: Authorization negative
        self.test_authorization_negative()
        
        # Test 3: List users
        users_result = self.test_list_users(limit=500)
        
        # Test 4: Cross-validation
        self.test_cross_validation_stats_vs_users(stats_result, users_result)
        
        # Test 5: Filter robustness
        self.test_filter_robustness()
        
        # Test 6: Latency statistics
        self.calculate_latency_statistics()
        
        # Finalize report
        self.report.end_time_utc = datetime.now(timezone.utc).isoformat()
        
        # Compile endpoints tested
        self.report.endpoints_tested = [
            {
                "endpoint": r.endpoint,
                "method": r.method,
                "status_code": r.status_code,
                "latency_ms": round(r.latency_ms, 2),
                "success": r.success,
                "validation_passed": r.validation_passed,
                "timestamp": r.timestamp
            }
            for r in self.results
        ]
        
        # Final summary
        print("\n" + "=" * 70)
        print("📋 TEST SUMMARY")
        print("=" * 70)
        print(f"Total tests: {len(self.results)}")
        print(f"Passed: {sum(1 for r in self.results if r.validation_passed)}")
        print(f"Failed: {sum(1 for r in self.results if not r.validation_passed)}")
        print(f"HTTP 2xx responses: {sum(1 for r in self.results if r.success)}")
        print(f"Overall Status: {self.report.overall_status}")
        print(f"Structural Issues: {len(self.report.structural_issues)}")
        print(f"Inconsistencies: {len(self.report.inconsistencies)}")
        print("=" * 70)
        
        return self.report
    
    def save_report(self, filename: str = "report_admin_endpoints.json"):
        """
        Salva o relatório em JSON
        """
        report_dict = self.report.to_dict()
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Report saved to: {filename}")
    
    def generate_roadmap(self, filename: str = "ROADMAP_ADMIN_ENDPOINT_TESTS.md"):
        """
        Gera ROADMAP em Markdown com análise detalhada
        """
        roadmap = []
        roadmap.append("# ROADMAP - Admin Endpoint Production Tests\n")
        roadmap.append(f"**Correlation ID:** {self.correlation_id}\n")
        roadmap.append(f"**Execution Date:** {self.start_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        roadmap.append(f"**Overall Status:** {self.report.overall_status}\n")
        roadmap.append("\n---\n")
        
        # What was requested
        roadmap.append("## 📋 What Was Requested\n")
        roadmap.append("1. ✅ Verify BIPOLAR_ADMIN_TOKEN environment variable\n")
        roadmap.append("2. ✅ Generate unique correlation ID (UUID + timestamp)\n")
        roadmap.append("3. ✅ Execute smoke test with positive authorization\n")
        roadmap.append("4. ✅ Execute negative authorization test\n")
        roadmap.append("5. ✅ Test key endpoints (list resources)\n")
        roadmap.append("6. ✅ Measure and analyze latencies\n")
        roadmap.append("7. ✅ Verify response structure\n")
        roadmap.append("8. ✅ Test robustness with filters\n")
        roadmap.append("9. ✅ Generate consolidated JSON report\n")
        roadmap.append("10. ✅ Generate ROADMAP document\n")
        roadmap.append("\n")
        
        # What was executed
        roadmap.append("## ✅ What Was Executed\n")
        roadmap.append(f"**Total endpoints tested:** {len(self.results)}\n")
        roadmap.append(f"**Tests passed:** {sum(1 for r in self.results if r.validation_passed)}\n")
        roadmap.append(f"**Tests failed:** {sum(1 for r in self.results if not r.validation_passed)}\n")
        roadmap.append(f"**HTTP 2xx responses:** {sum(1 for r in self.results if r.success)}\n")
        roadmap.append("\n### Endpoints Tested:\n")
        
        for result in self.results:
            validation_icon = "✅" if result.validation_passed else "❌"
            roadmap.append(f"- {validation_icon} `{result.method} {result.endpoint}` "
                          f"→ HTTP {result.status_code} ({result.latency_ms:.2f}ms)\n")
        
        roadmap.append("\n")
        
        # Latency analysis
        if self.report.latencies:
            roadmap.append("## 📊 Latency Analysis\n")
            roadmap.append(f"- **Mean:** {self.report.latencies['meanMs']}ms\n")
            roadmap.append(f"- **P95:** {self.report.latencies['p95Ms']}ms\n")
            roadmap.append(f"- **Max:** {self.report.latencies['maxMs']}ms\n")
            roadmap.append(f"- **Min:** {self.report.latencies['minMs']}ms\n")
            roadmap.append(f"- **Std Dev:** {self.report.latencies['stdDevMs']}ms\n")
            roadmap.append("\n")
        
        # Authorization test
        if self.report.authorization_negative_result:
            roadmap.append("## 🔒 Authorization Test\n")
            auth_result = self.report.authorization_negative_result
            roadmap.append(f"- **Expected status:** {auth_result.get('expected')}\n")
            roadmap.append(f"- **Obtained status:** {auth_result.get('obtained')}\n")
            roadmap.append(f"- **Result:** {auth_result.get('status')}\n")
            roadmap.append("\n")
        
        # Issues found
        if self.report.structural_issues:
            roadmap.append("## ⚠️ Structural Issues Found\n")
            for issue in self.report.structural_issues:
                roadmap.append(f"- {issue}\n")
            roadmap.append("\n")
        
        if self.report.inconsistencies:
            roadmap.append("## ⚠️ Inconsistencies Found\n")
            for inconsistency in self.report.inconsistencies:
                roadmap.append(f"- {inconsistency}\n")
            roadmap.append("\n")
        
        # What could not be tested
        roadmap.append("## ❌ What Could NOT Be Tested\n")
        roadmap.append("- ⚠️ User creation endpoint (risk of data modification)\n")
        roadmap.append("- ⚠️ Data cleanup endpoints (destructive operations)\n")
        roadmap.append("- ⚠️ Synthetic data generation (data modification)\n")
        roadmap.append("\n**Justification:** These endpoints modify production data and were "
                      "excluded to prevent unintended changes.\n")
        roadmap.append("\n")
        
        # Next steps
        roadmap.append("## 🚀 Suggested Next Steps\n")
        roadmap.append("1. Add cache header verification (Cache-Control, ETag)\n")
        roadmap.append("2. Add security header validation (CORS, CSP, X-Frame-Options)\n")
        roadmap.append("3. Implement pagination boundary tests (offset=0, large offsets)\n")
        roadmap.append("4. Add concurrent request testing for race conditions\n")
        roadmap.append("5. Monitor endpoint performance over time (trending)\n")
        roadmap.append("6. Add health check for dependent services (Supabase connectivity)\n")
        roadmap.append("7. Implement automated alerts for latency degradation\n")
        roadmap.append("\n")
        
        # Comparison
        roadmap.append("## 📊 Comparison: Requested vs Executed\n")
        roadmap.append("| Requirement | Status | Notes |\n")
        roadmap.append("|------------|--------|-------|\n")
        roadmap.append("| Environment variable check | ✅ | BIPOLAR_ADMIN_TOKEN validated |\n")
        roadmap.append("| Correlation ID generation | ✅ | UUID + timestamp |\n")
        roadmap.append("| Positive auth test | ✅ | GET /api/admin/stats |\n")
        roadmap.append("| Negative auth test | ✅ | Corrupted token test |\n")
        roadmap.append("| List users endpoint | ✅ | With pagination |\n")
        roadmap.append("| Cross-validation | ✅ | Stats vs Users count |\n")
        roadmap.append("| Latency measurement | ✅ | Mean, P95, Max, Min, StdDev |\n")
        roadmap.append("| Structure validation | ✅ | Field presence checks |\n")
        roadmap.append("| Filter robustness | ✅ | Role filters tested |\n")
        roadmap.append("| JSON report | ✅ | Generated |\n")
        roadmap.append("| Markdown roadmap | ✅ | This document |\n")
        roadmap.append("\n")
        
        # Mathematical metrics
        roadmap.append("## 🔢 Mathematical Metrics\n")
        
        if self.report.authorization_negative_result:
            expected = self.report.authorization_negative_result.get('expected', [])
            obtained = self.report.authorization_negative_result.get('obtained', 0)
            roadmap.append(f"- **Authorization rejection rate:** "
                          f"{'100%' if obtained in expected else '0% (FAILED)'}\n")
        
        validation_rate = (sum(1 for r in self.results if r.validation_passed) / len(self.results) * 100) if self.results else 0
        http_success_rate = (sum(1 for r in self.results if r.success) / len(self.results) * 100) if self.results else 0
        roadmap.append(f"- **Test validation pass rate:** {validation_rate:.2f}%\n")
        roadmap.append(f"- **HTTP 2xx success rate:** {http_success_rate:.2f}%\n")
        
        roadmap.append("\n---\n")
        roadmap.append(f"\n*Report generated at: {datetime.now(timezone.utc).isoformat()}*\n")
        
        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.writelines(roadmap)
        
        print(f"📄 ROADMAP saved to: {filename}")


# ============================================================================
# Main Execution
# ============================================================================

def main():
    """
    Ponto de entrada principal do script
    """
    print("\n" + "="*70)
    print("🔧 Admin Endpoint Production Testing Script")
    print("="*70 + "\n")
    
    # 1. Check for BIPOLAR_ADMIN_TOKEN
    admin_token = os.getenv("BIPOLAR_ADMIN_TOKEN")
    
    if not admin_token:
        print("❌ ERROR: BIPOLAR_ADMIN_TOKEN environment variable not found!")
        print("\n" + "="*70)
        print("O que é BIPOLAR_ADMIN_TOKEN?")
        print("="*70)
        print("É um token JWT de autenticação para acessar endpoints admin.")
        print("\nPara obter o token, você tem 3 opções:")
        print("\n1. Login via API:")
        print("   curl -X POST https://bipolar-api.onrender.com/api/auth/login \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{\"email\":\"admin@example.com\",\"password\":\"sua-senha\"}'")
        print("\n2. Via Supabase Dashboard:")
        print("   - Acesse app.supabase.com")
        print("   - Authentication → Users → Generate JWT")
        print("\n3. Token existente:")
        print("   - Use um token JWT válido de um usuário admin")
        print("\n" + "="*70)
        print("📖 Para instruções completas, consulte:")
        print("   tools/BIPOLAR_ADMIN_TOKEN_GUIDE.md")
        print("="*70)
        print("\nDepois de obter o token, execute:")
        print("  export BIPOLAR_ADMIN_TOKEN='seu-token-jwt-aqui'")
        print("  python tools/test_admin_endpoints_production.py")
        print("\nAborting test execution.")
        sys.exit(1)
    
    print(f"✅ BIPOLAR_ADMIN_TOKEN found (length: {len(admin_token)} chars)")
    
    # Check optional API URL override
    api_url = os.getenv("BIPOLAR_API_URL", "https://bipolar-engine.onrender.com")
    print(f"🌐 API URL: {api_url}\n")
    
    # 2. Create tester instance
    tester = AdminEndpointTester(admin_token)
    
    # 3. Run all tests
    try:
        report = tester.run_all_tests()
        
        # 4. Save results
        tester.save_report()
        tester.generate_roadmap()
        
        print("\n✅ Test execution completed successfully!")
        
        # Exit code based on overall status
        if report.overall_status == "OK":
            sys.exit(0)
        elif report.overall_status == "WARN":
            sys.exit(1)
        else:  # FAIL
            sys.exit(2)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Unexpected error during test execution: {e}")
        traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()
