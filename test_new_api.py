#!/usr/bin/env python3
"""
Test script for the new NextDraw project-based API
"""

import requests
import json
import time
import os
import sys
import argparse
from datetime import datetime

class APITester:
    def __init__(self, base_url='http://localhost:5000'):
        self.base_url = base_url
        self.test_results = []
        self.project_id = None

    def log(self, message, level='INFO'):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {level}: {message}")

    def test_endpoint(self, name, method, endpoint, **kwargs):
        """Test a single endpoint and record results"""
        url = f"{self.base_url}{endpoint}"
        self.log(f"Testing {name}: {method} {endpoint}")

        try:
            response = requests.request(method, url, **kwargs)
            success = response.status_code < 400

            self.test_results.append({
                'name': name,
                'endpoint': endpoint,
                'method': method,
                'status_code': response.status_code,
                'success': success,
                'response': response.json() if response.text else None
            })

            if success:
                self.log(f"✓ {name} passed (Status: {response.status_code})", 'SUCCESS')
                if response.text:
                    self.log(f"  Response: {json.dumps(response.json(), indent=2)[:200]}...")
            else:
                self.log(f"✗ {name} failed (Status: {response.status_code})", 'ERROR')
                if response.text:
                    self.log(f"  Error: {response.json()}", 'ERROR')

            return response

        except Exception as e:
            self.log(f"✗ {name} failed with exception: {str(e)}", 'ERROR')
            self.test_results.append({
                'name': name,
                'endpoint': endpoint,
                'method': method,
                'status_code': None,
                'success': False,
                'error': str(e)
            })
            return None

    def create_test_svg(self, filename='test_layer.svg', size='small'):
        """Create a simple test SVG file"""
        if size == 'small':
            svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="100mm" height="100mm" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="10" y="10" width="80" height="80" fill="none" stroke="black" stroke-width="1"/>
  <circle cx="50" cy="50" r="30" fill="none" stroke="black" stroke-width="1"/>
  <path d="M 25 50 L 75 50 M 50 25 L 50 75" stroke="black" stroke-width="1"/>
</svg>'''
        else:  # large
            # Create a larger SVG with many elements
            paths = []
            for i in range(100):
                x = 10 + (i % 10) * 8
                y = 10 + (i // 10) * 8
                paths.append(f'<circle cx="{x}" cy="{y}" r="3" fill="none" stroke="black"/>')

            svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="200mm" height="200mm" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
  <rect x="5" y="5" width="190" height="190" fill="none" stroke="black" stroke-width="1"/>
  {chr(10).join(paths)}
</svg>'''

        with open(filename, 'w') as f:
            f.write(svg_content)

        return filename

    def run_tests(self):
        """Run all API tests"""
        self.log("Starting NextDraw API Tests", 'INFO')
        self.log(f"Testing against: {self.base_url}", 'INFO')
        print("-" * 60)

        # Test 1: Health Check
        self.test_endpoint(
            "Health Check",
            "GET",
            "/health"
        )

        # Test 2: Initial Status
        response = self.test_endpoint(
            "Initial Status",
            "GET",
            "/status"
        )

        # Test 3: Create Project
        project_data = {
            "name": "Test Project",
            "description": "API test project",
            "total_layers": 3,
            "layer_names": {
                "layer_0": "Base Layer",
                "layer_1": "Middle Layer",
                "layer_2": "Top Layer"
            },
            "config": {
                "default_speed": 100,
                "pen_down_position": 90
            },
            "metadata": {
                "test_run": True,
                "created_by": "test_script"
            }
        }

        response = self.test_endpoint(
            "Create Project",
            "POST",
            "/project",
            json=project_data
        )

        if response and response.status_code == 201:
            self.project_id = response.json()['project']['id']
            self.log(f"Created project: {self.project_id}")

        # Test 4: Upload Layers
        for i in range(3):
            # Create test SVG
            svg_file = self.create_test_svg(f"test_layer_{i}.svg")

            with open(svg_file, 'rb') as f:
                self.test_endpoint(
                    f"Upload Layer {i}",
                    "POST",
                    f"/project/layer/layer_{i}",
                    files={'file': f}
                )

            # Clean up
            os.remove(svg_file)

        # Test 5: Check Project Status
        response = self.test_endpoint(
            "Project Status After Upload",
            "GET",
            "/status"
        )

        if response:
            project_status = response.json().get('project', {}).get('status')
            if project_status == 'ready':
                self.log("Project is ready for plotting!", 'SUCCESS')
            else:
                self.log(f"Project status: {project_status}", 'WARNING')

        # Test 6: Test Chunked Upload
        self.log("\nTesting chunked upload...", 'INFO')

        # Clear project first
        self.test_endpoint(
            "Clear Project for Chunked Test",
            "DELETE",
            "/project"
        )

        # Create new project for chunked upload
        chunk_project_data = {
            "name": "Chunked Upload Test",
            "total_layers": 1
        }

        response = self.test_endpoint(
            "Create Project for Chunks",
            "POST",
            "/project",
            json=chunk_project_data
        )

        # Simulate chunked upload
        large_svg = self.create_test_svg("large_test.svg", size="large")

        with open(large_svg, 'rb') as f:
            file_content = f.read()

        chunk_size = len(file_content) // 3 + 1
        total_chunks = 3
        file_id = "test_chunk_upload"

        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(file_content))
            chunk_data = file_content[start:end]

            self.test_endpoint(
                f"Upload Chunk {i}/{total_chunks}",
                "POST",
                "/project/layer/layer_0",
                files={'chunk_data': (f'chunk_{i}', chunk_data)},
                data={
                    'chunk_number': i,
                    'total_chunks': total_chunks,
                    'file_id': file_id,
                    'filename': 'large_test.svg'
                }
            )

        os.remove(large_svg)

        # Test 7: Configuration Endpoints
        self.test_endpoint(
            "Get Configuration",
            "GET",
            "/config"
        )

        config_update = {
            "pen_config": {
                "pen_up_position": 45,
                "pen_down_position": 85
            }
        }

        self.test_endpoint(
            "Update Configuration",
            "PUT",
            "/config",
            json=config_update
        )

        # Test 8: Plot Control (without actual plotting)
        self.log("\nTesting plot control endpoints...", 'INFO')

        # Note: These will fail if no plotter is connected, but we're testing the API responds correctly
        # Test with configuration parameters
        plot_config = {
            "speed": 75,
            "pen_up_position": 45,
            "pen_down_position": 85
        }

        self.test_endpoint(
            "Start Plot (will fail without plotter)",
            "POST",
            "/plot/layer_0",
            json=plot_config
        )

        self.test_endpoint(
            "Pause Plot",
            "POST",
            "/plot/pause"
        )

        self.test_endpoint(
            "Resume Plot",
            "POST",
            "/plot/resume"
        )

        self.test_endpoint(
            "Stop Plot",
            "POST",
            "/plot/stop"
        )

        # Test 9: Clear Project
        self.test_endpoint(
            "Clear Project",
            "DELETE",
            "/project"
        )

        # Test 10: Status After Clear
        self.test_endpoint(
            "Status After Clear",
            "GET",
            "/status"
        )

        # Test 11: Error Cases
        self.log("\nTesting error cases...", 'INFO')

        # Upload without project
        svg_file = self.create_test_svg("error_test.svg")
        with open(svg_file, 'rb') as f:
            self.test_endpoint(
                "Upload Without Project (should fail)",
                "POST",
                "/project/layer/layer_0",
                files={'file': f}
            )
        os.remove(svg_file)

        # Invalid layer ID
        self.test_endpoint(
            "Invalid Layer ID (should fail)",
            "POST",
            "/plot/invalid_layer"
        )

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for t in self.test_results if t['success'])
        failed_tests = total_tests - passed_tests

        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✓")
        print(f"Failed: {failed_tests} ✗")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")

        if failed_tests > 0:
            print("\nFailed Tests:")
            for test in self.test_results:
                if not test['success']:
                    print(f"  - {test['name']} ({test['method']} {test['endpoint']})")
                    if 'error' in test:
                        print(f"    Error: {test['error']}")

        print("\nNote: Some tests may fail if no plotter is connected.")
        print("This is expected and tests the API's error handling.\n")

def main():
    parser = argparse.ArgumentParser(description='Test NextDraw Project-Based API')
    parser.add_argument(
        '--url',
        default='http://localhost:5000',
        help='Base URL of the API (default: http://localhost:5000)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed response data'
    )

    args = parser.parse_args()

    tester = APITester(args.url)

    try:
        tester.run_tests()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
        tester.print_summary()
    except Exception as e:
        print(f"\n\nUnexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
