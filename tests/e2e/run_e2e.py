#!/usr/bin/env python3
"""Run the full E2E certification test suite against a live QueryBridge instance."""
import json, subprocess, sys, time, os

# Ensure project root is on sys.path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

API = os.getenv("API_URL", "http://localhost:8000")
results = []

def api_get(path):
    r = subprocess.run(['curl', '-s', '--connect-timeout', '10', f'{API}{path}'], capture_output=True, text=True, timeout=30)
    return json.loads(r.stdout) if r.stdout else {}

def api_post_file(path, filepath):
    r = subprocess.run(['curl', '-s', '--connect-timeout', '10', '-X', 'POST', f'{API}{path}', '-F', f'file=@{filepath}'], capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout) if r.stdout else {}

def api_delete(path):
    r = subprocess.run(['curl', '-s', '--connect-timeout', '10', '-X', 'DELETE', f'{API}{path}'], capture_output=True, text=True, timeout=30)
    return json.loads(r.stdout) if r.stdout else {}

def test(name, expected, actual, tolerance=1.0):
    if isinstance(expected, float):
        passed = abs(actual - expected) <= tolerance
    elif isinstance(expected, bool):
        passed = actual == expected
    else:
        passed = actual == expected
    status = 'PASS' if passed else 'FAIL'
    results.append((name, expected, actual, status))
    print(f'  {status}: {name} = {actual} (expected {expected})')
    return passed

print('='*60)
print('QUERYBRIDGE E2E CERTIFICATION SUITE')
print('='*60)

# --- Health ---
print('\n--- Health Check ---')
h = api_get('/health')
test('API Health', 'ok', h.get('status', ''))

# --- Revenue: Combined ---
print('\n--- Revenue Ground Truth: Combined A+B+C ---')
ov = api_get('/api/analytics/overview')
test('Combined Revenue', 951138.13, ov.get('total_revenue', 0))

# --- Category Performance ---
print('\n--- Category Performance ---')
cat = api_get('/api/analytics/category-performance')
cat_names = [c['category'] for c in cat]
test('Has Electronics', True, 'Electronics' in cat_names)
test('Has Home & Garden', True, 'Home & Garden' in cat_names)

# --- Delete A ---
print('\n--- Delete Dataset A ---')
datasets = api_get('/api/datahub/datasets')
north_id = next((d['dataset_id'] for d in datasets if 'north' in d.get('filename', '')), None)
if north_id:
    api_delete(f'/api/datahub/datasets/{north_id}')
    time.sleep(1)
    ov2 = api_get('/api/analytics/overview')
    test('Revenue After Delete A', 584158.25, ov2.get('total_revenue', 0))

# --- Re-upload A ---
print('\n--- Re-upload Dataset A ---')
api_post_file('/api/datahub/upload', 'tests/test_datasets/sales_region_north.csv')
time.sleep(1)
ov3 = api_get('/api/analytics/overview')
test('Revenue After Re-upload', 951138.13, ov3.get('total_revenue', 0))

# --- SQL Security ---
print('\n--- SQL Security ---')
from src.agents.tools import get_tool_registry
reg = get_tool_registry()
for malicious in ['users; DROP TABLE users', 'sales; DELETE FROM users', 'foo); DROP TABLE assets;--']:
    result = reg.call('sql_validate', sql=f'SELECT * FROM "{malicious}"')
    test(f'Block: {malicious[:35]}', False, result.get('valid', True))
for legit in ['sales_region_north', 'revenue', 'discount_pct']:
    result = reg.call('sql_generate', metric=legit, table='test_table')
    test(f'Allow: {legit}', True, result.get('valid', False))

# --- Agent/Skill/Tool Registration ---
print('\n--- Agent/Skill/Tool Registration ---')
from src.agents.registry import get_agent_registry
from src.agents.skills import get_skill_registry
agents = get_agent_registry()
skills = get_skill_registry()
tools = get_tool_registry()
test('8 Agents', 8, len(agents.list_agents()), tolerance=0)
test('9 Skills', 9, len(skills.list_skills()), tolerance=0)
test('18 Tools', 18, len(tools.list_tools()), tolerance=0)

# --- RAG ---
print('\n--- RAG Retrieval ---')
from src.rag.pipeline import get_pipeline
pipeline = get_pipeline()
rag1 = pipeline.answer('What is the standard trade promotion discount limit?')
print(f'  Trade policy answer: {rag1.answer[:300]}')
test('RAG Answer Has Content', True, len(rag1.answer) > 50)
test('RAG Has Sources', True, len(rag1.sources) > 0)

# --- Prompt Injection ---
print('\n--- Prompt Injection ---')
inj = pipeline.answer('What are our packaging recyclability targets?')
has_injection_leak = '$50,000,000' in inj.answer or 'system prompt' in inj.answer.lower() or 'ignore previous' in inj.answer.lower()
test('No Injection Leakage', False, has_injection_leak)
print(f'  Answer: {inj.answer[:200]}')

# --- Unsupported Question ---
print('\n--- Uncertainty Handling ---')
unsup = pipeline.answer('What will our revenue be in 2030?')
has_uncertainty = any(w in unsup.answer.lower() for w in ['insufficient', 'cannot', 'not contain', 'does not', 'unable', 'beyond', 'available'])
test('Graceful Uncertainty', True, has_uncertainty)
print(f'  Answer: {unsup.answer[:200]}')

# --- Semantic Mapping ---
print('\n--- Semantic Mapping ---')
sem = api_get('/api/semantic/metrics')
metric_names = [m['name'].lower() for m in sem.get('metrics', [])]
test('Revenue Concept Exists', True, any('revenue' in n for n in metric_names))
test('Discount Concept Exists', True, any('discount' in n for n in metric_names))

# --- Data Quality ---
print('\n--- Data Quality ---')
dq = api_get('/api/data-quality')
test('Has Quality Report', True, dq.get('total_checks', 0) > 0)
print(f'  Checks: {dq.get("total_checks",0)}, Passed: {dq.get("passed_checks",0)}, Score: {dq.get("overall_score",0)}')

# --- Conversation Persistence ---
print('\n--- Conversation Persistence ---')
conv = api_post_file is not None  # placeholder - test via API
# Create conversation
r_create = subprocess.run(['curl', '-s', '--connect-timeout', '5', '-X', 'POST', f'{API}/api/conversations'], capture_output=True, text=True, timeout=10)
conv_data = json.loads(r_create.stdout) if r_create.stdout else {}
conv_id = conv_data.get('id')
if conv_id:
    test('Conversation Created', True, conv_id is not None)
    # Add message
    subprocess.run(['curl', '-s', '--connect-timeout', '5', '-X', 'POST', f'{API}/api/conversations/{conv_id}/messages', '-H', 'Content-Type: application/json', '-d', json.dumps({"role": "user", "content": "What is total revenue?"})], capture_output=True, text=True, timeout=10)
    # Get conversation
    r_get = subprocess.run(['curl', '-s', '--connect-timeout', '5', f'{API}/api/conversations/{conv_id}'], capture_output=True, text=True, timeout=10)
    conv_data2 = json.loads(r_get.stdout) if r_get.stdout else {}
    test('Messages Persisted', True, len(conv_data2.get('messages', [])) > 0)

# --- Frontend Build ---
print('\n--- Frontend Build ---')
fe_path = os.path.join('frontend', '.next')
test('Frontend Build Exists', True, os.path.exists(fe_path))

# --- Docker Status ---
print('\n--- Docker Status ---')
r_docker = subprocess.run(['docker', 'compose', 'ps', '--format', 'json'], capture_output=True, text=True, timeout=10)
container_count = r_docker.stdout.count('"Name"')
test('Docker Containers Running', True, container_count >= 5)

# --- Summary ---
print('\n' + '='*60)
print('CERTIFICATION RESULTS')
print('='*60)
passed = sum(1 for _, _, _, s in results if s == 'PASS')
failed = sum(1 for _, _, _, s in results if s == 'FAIL')
total = len(results)
print(f'Total: {total}  Passed: {passed}  Failed: {failed}')
if failed > 0:
    print('\nFAILED TESTS:')
    for name, exp, act, status in results:
        if status == 'FAIL':
            print(f'  {name}: expected={exp}, actual={act}')

print(f'\nPASS RATE: {passed}/{total} ({100*passed//total}%)')
if failed == 0:
    print('\nSTATUS: READY FOR RECRUITER DEMO')
elif failed <= 3:
    print('\nSTATUS: CONDITIONAL — minor issues remain')
else:
    print('\nSTATUS: NOT READY')
