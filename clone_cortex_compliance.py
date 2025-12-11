#!/usr/bin/env python3
"""
Cortex Compliance Cloner Script
Clone a compliance standard with all controls and rules from Cortex XSIAM/XDR

Usage:
    python clone_cortex_compliance.py --key YOUR_API_KEY --id YOUR_KEY_ID --tenant YOUR_TENANT_FQDN --standard "Standard Name" --prefix "Clone - "
"""

import requests
import json
import sys
import time
import argparse
import logging
import uuid
from typing import Optional, Dict, List, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_API_KEY = ""
DEFAULT_API_KEY_ID = ""
DEFAULT_FQDN = ""
DEFAULT_STD_NAME = ""
DEFAULT_PREFIX = "Clone - "


class CortexComplianceCloner:
    FALLBACK_CATEGORY = "Access Control"
    FALLBACK_SUBCATEGORY = "1.1"
    
    def __init__(self, api_key: str, api_key_id: str, fqdn: str, prefix: str = "Clone - "):
        self.api_key = api_key
        self.api_key_id = api_key_id
        self.prefix = prefix
        
        if not fqdn.startswith("https://"):
            self.base_url = f"https://{fqdn}/public_api/v1/compliance"
        else:
            self.base_url = f"{fqdn}/public_api/v1/compliance"
        
        self.headers = {
            "x-xdr-auth-id": api_key_id,
            "Authorization": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        self.valid_categories = []
        self.valid_subcategories = []
        self.failed_controls = []
        self.failed_rules = []
    
    def post_request(self, endpoint: str, payload: Dict, timeout: int = 90) -> Optional[requests.Response]:
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=timeout)
            if response.status_code >= 400:
                logger.debug(f"API error {response.status_code} from {endpoint}: {response.text}")
            return response
        except requests.exceptions.RequestException as e:
            logger.debug(f"Connection error to {endpoint}: {e}")
            return None
    
    def get_val(self, obj: Dict, key: str, default: Any = None) -> Any:
        if not obj:
            return default
        if key in obj:
            return obj[key]
        if key.lower() in obj:
            return obj[key.lower()]
        if key.upper() in obj:
            return obj[key.upper()]
        return default
    
    def clean_severity(self, severity_code: str) -> str:
        if not severity_code:
            return "low"
        s = str(severity_code).lower()
        if "critical" in s:
            return "critical"
        if "high" in s:
            return "high"
        if "medium" in s:
            return "medium"
        if "info" in s:
            return "info"
        return "low"
    
    def fetch_valid_categories(self) -> bool:
        logger.info("Fetching valid categories and subcategories...")
        response = self.post_request("get_control_categories_and_subcategories", {"request_data": {}})
        if response and response.status_code == 200:
            reply = response.json().get('reply', {})
            data = reply.get('data', {})
            self.valid_categories = data.get('categories', [])
            self.valid_subcategories = data.get('subcategories', [])
            logger.info(f"Found {len(self.valid_categories)} categories and {len(self.valid_subcategories)} subcategories")
            return True
        return False
    
    def find_closest_category(self, original_category: str) -> str:
        if not original_category:
            return self.FALLBACK_CATEGORY
        
        if original_category in self.valid_categories:
            return original_category
        
        orig_lower = original_category.lower()
        for cat in self.valid_categories:
            if cat.lower() == orig_lower:
                return cat
            if orig_lower in cat.lower() or cat.lower() in orig_lower:
                return cat
        
        logger.warning(f"Category '{original_category}' not found, using fallback: {self.FALLBACK_CATEGORY}")
        return self.FALLBACK_CATEGORY
    
    def find_closest_subcategory(self, original_subcategory: str) -> Optional[str]:
        if not original_subcategory:
            return None
        
        if original_subcategory in self.valid_subcategories:
            return original_subcategory
        
        for sub in self.valid_subcategories:
            if sub.lower() == original_subcategory.lower():
                return sub
        
        return None
    
    def find_standard_by_name(self, standard_name: str) -> Optional[Dict]:
        logger.info(f"Searching for standard: {standard_name}")
        
        response = self.post_request("get_standards", {
            "request_data": {
                "filters": [{"field": "name", "operator": "eq", "value": standard_name}]
            }
        })
        
        if response and response.status_code == 200:
            reply = response.json().get('reply', {})
            standards = reply.get('standards') or reply.get('data', [])
            if standards:
                return standards[0]
        
        logger.info("Filter didn't work, scanning pages...")
        search_from = 0
        while True:
            response = self.post_request("get_standards", {
                "request_data": {
                    "search_from": search_from,
                    "search_to": search_from + 100
                }
            })
            
            if not response or response.status_code != 200:
                break
            
            page_data = response.json().get('reply', {}).get('standards', [])
            if not page_data:
                break
            
            for std in page_data:
                if std.get('name') == standard_name:
                    return std
            
            search_from += 100
        
        return None
    
    def check_standard_exists(self, standard_name: str) -> Optional[str]:
        response = self.post_request("get_standards", {
            "request_data": {
                "filters": [{"field": "name", "operator": "eq", "value": standard_name}]
            }
        })
        
        if response and response.status_code == 200:
            standards = response.json().get('reply', {}).get('standards', [])
            if standards:
                return standards[0].get('id')
        return None
    
    def create_standard(self, name: str, description: str = "", labels: Optional[List[str]] = None) -> Optional[str]:
        logger.info(f"Creating new standard: {name}")
        
        payload = {
            "request_data": {
                "standard_name": name,
                "description": description or "",
                "labels": labels or [],
                "controls_ids": []
            }
        }
        
        response = self.post_request("add_standard", payload)
        
        if response and response.status_code == 200:
            logger.info("Standard created successfully")
            time.sleep(2)
            
            new_id = self.check_standard_exists(name)
            if new_id:
                return new_id
            else:
                logger.error("Could not find newly created standard")
                return None
        else:
            error_msg = response.text if response else "No response"
            logger.error(f"Failed to create standard: {error_msg}")
            return None
    
    def get_control_details(self, control_id: str) -> Optional[Dict]:
        response = self.post_request("get_control", {"request_data": {"id": control_id}})
        
        if response and response.status_code == 200:
            reply = response.json().get('reply', {})
            controls = reply.get('control', [])
            if controls and len(controls) > 0:
                return controls[0]
        return None
    
    def sanitize_rules(self, rule_list: List[Dict]) -> List[Dict]:
        clean_rules = []
        
        for rule in rule_list:
            try:
                name = self.get_val(rule, 'name')
                logical_id = self.get_val(rule, 'logical_id')
                
                if not name or not logical_id:
                    logger.debug(f"Skipping rule without name or logical_id: {rule}")
                    continue
                
                raw_severity = self.get_val(rule, 'severity')
                clean_severity = self.clean_severity(raw_severity)
                
                remediation = self.get_val(rule, 'remediation_steps') or self.get_val(rule, 'mitigation') or ""
                
                original_type = self.get_val(rule, 'type') or "Identity"
                if original_type != "Identity":
                    logger.warning(f"Rule type '{original_type}' not supported by API, using 'Identity' for rule: {name[:50]}")
                
                unique_logical_id = f"{self.prefix.replace(' ', '_')}{logical_id}"[:100]
                
                clean_rule = {
                    "name": name[:200],
                    "description": (self.get_val(rule, 'description') or "")[:2000],
                    "type": "Identity",
                    "logical_id": unique_logical_id,
                    "severity": clean_severity,
                    "scannable_assets": [],
                    "remediation_steps": remediation[:2000],
                    "generate_findings": bool(self.get_val(rule, 'generate_findings', True)),
                    "generate_issues": bool(self.get_val(rule, 'generate_issues', True)),
                    "generate_scan_logs": bool(self.get_val(rule, 'generate_scan_logs', True))
                }
                
                logger.debug(f"Sanitized rule: {clean_rule['name']}")
                clean_rules.append(clean_rule)
                
            except Exception as e:
                logger.debug(f"Skipping rule due to error: {e}")
                continue
        
        return clean_rules
    
    def create_control(self, name: str, category: str, description: str = "", 
                       subcategory: Optional[str] = None, severity: Optional[str] = None) -> Optional[str]:
        valid_category = self.find_closest_category(category)
        
        valid_subcategory = None
        if subcategory and isinstance(subcategory, str) and subcategory.strip():
            valid_subcategory = self.find_closest_subcategory(subcategory.strip())
        
        if not valid_subcategory and self.valid_subcategories:
            valid_subcategory = self.valid_subcategories[0]
            logger.debug(f"Using default subcategory: {valid_subcategory}")
        
        clean_severity = self.clean_severity(severity) if severity else "medium"
        
        payload = {
            "request_data": {
                "control_name": name[:200],
                "category": valid_category,
                "description": description or "",
                "subcategory": valid_subcategory or "1.1",
                "severity": clean_severity
            }
        }
        
        logger.debug(f"Creating control with payload: {payload}")
        
        response = self.post_request("add_control", payload)
        
        if not response:
            logger.warning(f"No response when creating control '{name}'")
            return None
            
        if response.status_code == 200:
            reply = response.json().get('reply', {})
            control_id = reply.get('control_id')
            
            if control_id:
                return control_id
            
            for attempt in range(3):
                time.sleep(1.5)
                search_response = self.post_request("get_controls", {
                    "request_data": {
                        "filters": [{"field": "name", "operator": "eq", "value": name[:200]}]
                    }
                })
                
                if search_response and search_response.status_code == 200:
                    controls = search_response.json().get('reply', {}).get('controls', [])
                    if controls:
                        return controls[0].get('id')
            
            return None
        else:
            logger.warning(f"Failed to create control '{name}' (HTTP {response.status_code}): {response.text}")
            return None
    
    def add_rules_to_control(self, control_id: str, control_name: str, rules: List[Dict], max_retries: int = 3) -> tuple:
        if not rules:
            return (0, 0)
        
        clean_rules = self.sanitize_rules(rules)
        if not clean_rules:
            logger.debug("No valid rules to add after sanitization")
            return (0, len(rules))
        
        response = None
        for attempt in range(max_retries):
            response = self.post_request("add_rules_to_control", {
                "request_data": {
                    "control_id": control_id,
                    "rules": clean_rules
                }
            })
            
            if response and response.status_code == 200:
                return (len(clean_rules), 0)
            
            if attempt < max_retries - 1:
                wait_time = 2 * (attempt + 1)
                logger.debug(f"Retry {attempt + 1}/{max_retries} for adding rules to '{control_name}', waiting {wait_time}s...")
                time.sleep(wait_time)
        
        error_msg = response.text if response else "No response"
        logger.warning(f"Failed to add {len(clean_rules)} rules to control '{control_name}' after {max_retries} attempts: {error_msg}")
        self.failed_rules.append({
            "control_id": control_id,
            "control_name": control_name,
            "rules_count": len(clean_rules),
            "error": error_msg
        })
        return (0, len(clean_rules))
    
    def link_controls_to_standard(self, standard_id: str, control_ids: List[str]) -> bool:
        response = self.post_request("get_standards", {
            "request_data": {
                "filters": [{"field": "id", "operator": "eq", "value": standard_id}]
            }
        })
        
        existing_controls = []
        if response and response.status_code == 200:
            standards = response.json().get('reply', {}).get('standards', [])
            if standards:
                existing_controls = standards[0].get('controls_ids') or []
        
        combined_controls = list(set(existing_controls + control_ids))
        
        response = self.post_request("edit_standard", {
            "request_data": {
                "id": standard_id,
                "controls_ids": combined_controls
            }
        })
        
        if response and response.status_code == 200:
            return True
        else:
            error_msg = response.text if response else "No response"
            logger.error(f"Failed to link controls: {error_msg}")
            return False
    
    def clone_standard(self, source_standard_name: str) -> bool:
        print(f"\n{'='*60}")
        print("CORTEX COMPLIANCE CLONER")
        print(f"{'='*60}")
        print(f"Source Standard: {source_standard_name}")
        print(f"Target Prefix: {self.prefix}")
        print(f"{'='*60}\n")
        
        self.fetch_valid_categories()
        
        print("[STEP 1] Finding source standard...")
        source_standard = self.find_standard_by_name(source_standard_name)
        
        if not source_standard:
            print(f"ERROR: Standard '{source_standard_name}' not found")
            return False
        
        control_ids = source_standard.get('controls_ids', [])
        print(f"Found standard with {len(control_ids)} controls")
        
        new_standard_name = f"{self.prefix}{source_standard_name}"[:200]
        
        print(f"\n[STEP 2] Creating/Finding target standard: {new_standard_name}")
        
        existing_id = self.check_standard_exists(new_standard_name)
        if existing_id:
            new_standard_id = existing_id
            print(f"Target standard already exists. ID: {new_standard_id}")
        else:
            new_standard_id = self.create_standard(
                name=new_standard_name,
                description=source_standard.get('description', ''),
                labels=source_standard.get('labels', [])
            )
            
            if not new_standard_id:
                print("ERROR: Failed to create target standard")
                return False
            print(f"Created new standard. ID: {new_standard_id}")
        
        print(f"\n[STEP 3] Creating {len(control_ids)} controls...")
        new_control_ids = []
        rules_stats = {"total": 0, "success": 0, "failed": 0}
        pending_rules = []
        
        for i, old_control_id in enumerate(control_ids, 1):
            print(f"  [{i}/{len(control_ids)}] Creating control...", end=" ", flush=True)
            
            source_control = self.get_control_details(old_control_id)
            if not source_control:
                print("SKIP (fetch failed)")
                continue
            
            original_name = self.get_val(source_control, 'control_name') or self.get_val(source_control, 'name') or f"Control_{old_control_id}"
            new_control_name = f"{self.prefix}{original_name}"[:200]
            
            category = self.get_val(source_control, 'category') or "Access Control"
            subcategory = self.get_val(source_control, 'subcategory')
            description = self.get_val(source_control, 'description') or ""
            severity = self.get_val(source_control, 'severity')
            
            new_control_id = self.create_control(
                name=new_control_name,
                category=category,
                description=description,
                subcategory=subcategory,
                severity=severity
            )
            
            if not new_control_id:
                print("FAILED")
                continue
            
            new_control_ids.append(new_control_id)
            
            raw_rules = self.get_val(source_control, 'compliance_rules') or []
            if raw_rules:
                pending_rules.append({
                    "control_id": new_control_id,
                    "control_name": new_control_name,
                    "rules": raw_rules
                })
                rules_stats["total"] += len(raw_rules)
                print(f"OK ({len(raw_rules)} rules pending)", flush=True)
            else:
                print("OK", flush=True)
        
        print(f"\n[STEP 4] Linking {len(new_control_ids)} controls to standard...")
        if new_control_ids:
            if self.link_controls_to_standard(new_standard_id, new_control_ids):
                print("SUCCESS: Controls linked to standard")
            else:
                print("WARNING: Failed to link some controls")
        else:
            print("WARNING: No controls to link")
        
        if pending_rules:
            print(f"\n[STEP 5] Adding rules to {len(pending_rules)} controls...")
            time.sleep(2)
            for i, pr in enumerate(pending_rules, 1):
                print(f"  [{i}/{len(pending_rules)}] Adding {len(pr['rules'])} rules to {pr['control_name'][:30]}...", end=" ", flush=True)
                success_count, fail_count = self.add_rules_to_control(pr['control_id'], pr['control_name'], pr['rules'])
                rules_stats["success"] += success_count
                rules_stats["failed"] += fail_count
                if success_count > 0:
                    print(f"OK [+{success_count}]", flush=True)
                else:
                    print(f"FAILED", flush=True)
                time.sleep(2)
        
        print(f"\n{'='*60}")
        print("CLONE SUMMARY")
        print(f"{'='*60}")
        print(f"Source Standard: {source_standard_name}")
        print(f"Target Standard: {new_standard_name}")
        print(f"Target Standard ID: {new_standard_id}")
        print(f"Controls Cloned: {len(new_control_ids)}/{len(control_ids)}")
        print(f"Rules Added: {rules_stats['success']}/{rules_stats['total']}")
        if rules_stats["failed"] > 0:
            print(f"Rules Failed: {rules_stats['failed']}")
        if self.failed_rules:
            print(f"\nFailed Rule Details:")
            for fr in self.failed_rules:
                print(f"  - Control '{fr['control_name']}': {fr['rules_count']} rules failed")
        print(f"{'='*60}\n")
        
        return len(new_control_ids) > 0


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Clone a Cortex compliance standard with all controls and rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clone_cortex_compliance.py --key YOUR_API_KEY --id 1 --tenant api-example.xdr.eu.paloaltonetworks.com --standard "CIS AWS Foundations Benchmark" --prefix "MyCompany - "
  
  python clone_cortex_compliance.py --standard "ISO 27001" --prefix "Cloned - "
        """
    )
    
    parser.add_argument("--key", default=DEFAULT_API_KEY, help="API Key")
    parser.add_argument("--id", default=DEFAULT_API_KEY_ID, help="API Key ID")
    parser.add_argument("--tenant", default=DEFAULT_FQDN, help="Tenant FQDN (e.g., api-example.xdr.eu.paloaltonetworks.com)")
    parser.add_argument("--standard", default=DEFAULT_STD_NAME, help="Name of the standard to clone")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Prefix for cloned items (default: 'Clone - ')")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    return parser.parse_args()


def main():
    args = parse_arguments()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if not args.key or not args.id or not args.tenant:
        print("ERROR: API Key, API Key ID, and Tenant FQDN are required.")
        print("Use --help for usage information.")
        sys.exit(1)
    
    if not args.standard:
        print("ERROR: Standard name is required.")
        print("Use --help for usage information.")
        sys.exit(1)
    
    cloner = CortexComplianceCloner(
        api_key=args.key,
        api_key_id=args.id,
        fqdn=args.tenant,
        prefix=args.prefix
    )
    
    success = cloner.clone_standard(args.standard)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
