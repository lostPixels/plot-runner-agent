#!/usr/bin/env python3
"""
Test script for NextDraw Plotter API
Validates API endpoints and functionality
"""

import requests
import json
import time
import sys
from datetime import datetime

class NextDrawAPITester:
    def __init__(self, base_url="http://localhost"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.test_results = []
    
    def log_test(self, test_name, success, message="", response_data=None):
        """Log test result"""
        status = "PASS" if success else "FAIL"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        result = {
            "timestamp": timestamp,
            "test": test_name,
            "status": status,
            "message": message,
            "response_data": response_data
        }
        
        self.test_results.append(result)
        print(f"[{timestamp}] {status}: {test_name} - {message}")
        
        if response_data and not success:
            print(f"  Response: {json.dumps(response_data, indent=2)}")
    
    def test_health_check(self):
        """Test health check endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    self.log_test("Health Check", True, "API is healthy")
                    return True
                else:
                    self.log_test("Health Check", False, "Unhealthy status", data)
            else:
                self.log_test("Health Check", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Health Check", False, f"Request failed: {str(e)}")
        
        return False
    
    def test_status_endpoint(self):
        """Test status endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/status", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                required_keys = ["plotter", "queue", "app", "config"]
                
                if all(key in data for key in required_keys):
                    plotter_status = data["plotter"]["status"]
                    self.log_test("Status Endpoint", True, f"Plotter status: {plotter_status}")
                    return True
                else:
                    self.log_test("Status Endpoint", False, "Missing required keys", data)
            else:
                self.log_test("Status Endpoint", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Status Endpoint", False, f"Request failed: {str(e)}")
        
        return False
    
    def test_config_endpoints(self):
        """Test configuration endpoints"""
        try:
            # Test GET config
            response = self.session.get(f"{self.base_url}/config", timeout=5)
            
            if response.status_code == 200:
                config = response.json()
                if "plotter_settings" in config:
                    self.log_test("Get Config", True, "Configuration retrieved")
                    
                    # Test PUT config (update speed)
                    original_speed = config["plotter_settings"].get("speed_pendown", 25)
                    test_speed = 30 if original_speed != 30 else 35
                    
                    update_data = {
                        "plotter_settings": {
                            "speed_pendown": test_speed
                        }
                    }
                    
                    response = self.session.put(
                        f"{self.base_url}/config",
                        json=update_data,
                        timeout=5
                    )
                    
                    if response.status_code == 200:
                        # Verify update
                        response = self.session.get(f"{self.base_url}/config", timeout=5)
                        if response.status_code == 200:
                            updated_config = response.json()
                            new_speed = updated_config["plotter_settings"]["speed_pendown"]
                            
                            if new_speed == test_speed:
                                self.log_test("Update Config", True, f"Speed updated to {test_speed}")
                                
                                # Restore original value
                                restore_data = {
                                    "plotter_settings": {
                                        "speed_pendown": original_speed
                                    }
                                }
                                self.session.put(f"{self.base_url}/config", json=restore_data)
                                return True
                            else:
                                self.log_test("Update Config", False, "Config not updated properly")
                        else:
                            self.log_test("Update Config", False, "Could not verify update")
                    else:
                        self.log_test("Update Config", False, f"HTTP {response.status_code}")
                else:
                    self.log_test("Get Config", False, "Invalid config structure", config)
            else:
                self.log_test("Get Config", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Config Endpoints", False, f"Request failed: {str(e)}")
        
        return False
    
    def test_utility_commands(self):
        """Test utility commands"""
        utility_tests = [
            ("raise_pen", "Raise pen"),
            ("lower_pen", "Lower pen"),
            ("toggle_pen", "Toggle pen"),
        ]
        
        all_passed = True
        
        for command, description in utility_tests:
            try:
                response = self.session.post(
                    f"{self.base_url}/utility/{command}",
                    json={},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("result", {}).get("success"):
                        self.log_test(f"Utility: {command}", True, description)
                    else:
                        self.log_test(f"Utility: {command}", False, "Command failed", data)
                        all_passed = False
                else:
                    self.log_test(f"Utility: {command}", False, f"HTTP {response.status_code}")
                    all_passed = False
                
                # Small delay between commands
                time.sleep(1)
                
            except Exception as e:
                self.log_test(f"Utility: {command}", False, f"Request failed: {str(e)}")
                all_passed = False
        
        return all_passed
    
    def test_job_endpoints(self):
        """Test job management endpoints"""
        try:
            # Test GET jobs (should be empty initially)
            response = self.session.get(f"{self.base_url}/jobs", timeout=5)
            
            if response.status_code == 200:
                self.log_test("Get Jobs", True, "Jobs endpoint accessible")
                
                # Test submitting a simple SVG job
                test_svg = '''<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="50" cy="50" r="40" stroke="black" stroke-width="2" fill="none"/>
                </svg>'''
                
                job_data = {
                    "name": "API_Test_Job",
                    "description": "Test job from API validation script",
                    "svg_content": test_svg,
                    "config": {
                        "speed_pendown": 10,  # Very slow for safety
                        "report_time": True
                    }
                }
                
                response = self.session.post(
                    f"{self.base_url}/plot",
                    json=job_data,
                    timeout=10
                )
                
                if response.status_code == 201:
                    job_result = response.json()
                    job_id = job_result.get("job_id")
                    
                    if job_id:
                        self.log_test("Submit Job", True, f"Job {job_id} submitted")
                        
                        # Wait a moment and check job status
                        time.sleep(2)
                        
                        response = self.session.get(f"{self.base_url}/jobs/{job_id}")
                        if response.status_code == 200:
                            job_info = response.json()
                            status = job_info.get("status", "unknown")
                            self.log_test("Get Job Info", True, f"Job status: {status}")
                            
                            # Cancel the job if it's still queued
                            if status in ["queued", "running"]:
                                response = self.session.delete(f"{self.base_url}/jobs/{job_id}")
                                if response.status_code == 200:
                                    self.log_test("Cancel Job", True, "Job cancelled successfully")
                                    # Test start_mm parameter
                                    return self.test_start_mm_parameter()
                            
                            # Test start_mm parameter
                            return self.test_start_mm_parameter()
                        else:
                            self.log_test("Get Job Info", False, f"HTTP {response.status_code}")
                    else:
                        self.log_test("Submit Job", False, "No job ID returned", job_result)
                else:
                    self.log_test("Submit Job", False, f"HTTP {response.status_code}")
            else:
                self.log_test("Get Jobs", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Job Endpoints", False, f"Request failed: {str(e)}")
        
        return False
    
    def test_start_mm_parameter(self):
        """Test start_mm parameter functionality"""
        try:
            # Test SVG with multiple paths for resume functionality
            test_svg = '''<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 20 L 180 20 L 180 180 L 20 180 Z" stroke="black" stroke-width="2" fill="none"/>
                <circle cx="100" cy="100" r="30" stroke="black" stroke-width="2" fill="none"/>
            </svg>'''
            
            # Test with start_mm parameter
            job_data = {
                "name": "API_Test_Job_StartMM",
                "description": "Test job with start_mm parameter",
                "svg_content": test_svg,
                "start_mm": 10.5,  # Start 10.5mm into the plot
                "config": {
                    "speed_pendown": 10,
                    "report_time": True
                }
            }
            
            response = self.session.post(
                f"{self.base_url}/plot",
                json=job_data,
                timeout=10
            )
            
            if response.status_code == 201:
                job_result = response.json()
                job_id = job_result.get("job_id")
                
                if job_id:
                    self.log_test("Submit Job with start_mm", True, f"Job {job_id} with start_mm=10.5 submitted")
                    
                    # Cancel the job immediately for safety
                    time.sleep(1)
                    response = self.session.delete(f"{self.base_url}/jobs/{job_id}")
                    if response.status_code == 200:
                        self.log_test("Cancel start_mm Job", True, "Job with start_mm cancelled successfully")
                        
                        # Test invalid start_mm parameter
                        return self.test_invalid_start_mm()
                    else:
                        self.log_test("Cancel start_mm Job", False, f"HTTP {response.status_code}")
                        return False
                else:
                    self.log_test("Submit Job with start_mm", False, "No job ID returned", job_result)
            else:
                self.log_test("Submit Job with start_mm", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Test start_mm Parameter", False, f"Request failed: {str(e)}")
        
        return False
    
    def test_invalid_start_mm(self):
        """Test invalid start_mm parameter handling"""
        try:
            test_svg = '''<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="40" stroke="black" stroke-width="2" fill="none"/>
            </svg>'''
            
            # Test with invalid start_mm parameter
            job_data = {
                "name": "API_Test_Job_Invalid_StartMM",
                "description": "Test job with invalid start_mm parameter",
                "svg_content": test_svg,
                "start_mm": "invalid_value",  # Invalid value
                "config": {
                    "speed_pendown": 10,
                    "report_time": True
                }
            }
            
            response = self.session.post(
                f"{self.base_url}/plot",
                json=job_data,
                timeout=10
            )
            
            if response.status_code == 400:
                error_data = response.json()
                if "start_mm must be a valid number" in error_data.get("error", ""):
                    self.log_test("Invalid start_mm Parameter", True, "Properly rejected invalid start_mm")
                    return True
                else:
                    self.log_test("Invalid start_mm Parameter", False, "Wrong error message", error_data)
            else:
                self.log_test("Invalid start_mm Parameter", False, f"Expected HTTP 400, got {response.status_code}")
                
        except Exception as e:
            self.log_test("Test Invalid start_mm", False, f"Request failed: {str(e)}")
        
        return False

    def test_logs_endpoint(self):
        """Test logs endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/logs?lines=10", timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if "logs" in data and isinstance(data["logs"], list):
                    log_count = len(data["logs"])
                    self.log_test("Logs Endpoint", True, f"Retrieved {log_count} log entries")
                    return True
                else:
                    self.log_test("Logs Endpoint", False, "Invalid logs format", data)
            else:
                self.log_test("Logs Endpoint", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Logs Endpoint", False, f"Request failed: {str(e)}")
        
        return False
    
    def run_all_tests(self):
        """Run all API tests"""
        print("Starting NextDraw API Tests")
        print("=" * 40)
        
        tests = [
            ("Health Check", self.test_health_check),
            ("Status Endpoint", self.test_status_endpoint),
            ("Configuration", self.test_config_endpoints),
            ("Utility Commands", self.test_utility_commands),
            ("Job Management", self.test_job_endpoints),
            ("Logs Endpoint", self.test_logs_endpoint),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\nRunning {test_name} tests...")
            try:
                if test_func():
                    passed += 1
            except KeyboardInterrupt:
                print("\nTests interrupted by user")
                break
            except Exception as e:
                print(f"Unexpected error in {test_name}: {str(e)}")
        
        # Summary
        print("\n" + "=" * 40)
        print("Test Summary")
        print("=" * 40)
        print(f"Tests passed: {passed}/{total}")
        print(f"Success rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            print("🎉 All tests passed! API is working correctly.")
            return True
        else:
            print("⚠️  Some tests failed. Check the output above for details.")
            return False
    
    def save_results(self, filename="test_results.json"):
        """Save test results to file"""
        try:
            with open(filename, 'w') as f:
                json.dump({
                    "test_run": datetime.now().isoformat(),
                    "base_url": self.base_url,
                    "results": self.test_results
                }, f, indent=2)
            print(f"Test results saved to {filename}")
        except Exception as e:
            print(f"Failed to save results: {str(e)}")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test NextDraw Plotter API")
    parser.add_argument(
        "--url",
        default="http://localhost",
        help="Base URL of the API (default: http://localhost)"
    )
    parser.add_argument(
        "--save-results",
        action="store_true",
        help="Save test results to JSON file"
    )
    
    args = parser.parse_args()
    
    tester = NextDrawAPITester(args.url)
    
    try:
        success = tester.run_all_tests()
        
        if args.save_results:
            tester.save_results()
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\nTest run interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"Test run failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()