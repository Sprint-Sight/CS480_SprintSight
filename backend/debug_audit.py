from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def login(email: str, password: str) -> str:
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    print('login', email, response.status_code, response.json())
    return response.json()['access_token']

instructor_headers = {'Authorization': 'Bearer ' + login('faculty@sprintsight.edu', 'password123')}
admin_headers = {'Authorization': 'Bearer ' + login('admin@sprintsight.edu', 'password123')}

course = client.post('/api/v1/courses', json={
    'code': 'CS505',
    'name': 'Scoped Audit Course',
    'section': 'A',
    'year': 2026,
    'term': 'Fall',
}, headers=instructor_headers)
print('course', course.status_code, course.json())

admin_user = client.post('/api/v1/users', json={
    'email': 'audit.admin.check@sprintsight.edu',
    'full_name': 'Audit Admin Check',
    'role': 'admin',
    'password': 'temporary123',
}, headers=admin_headers)
print('admin_user', admin_user.status_code, admin_user.json())

instr = client.get('/api/v1/audit/actions', headers=instructor_headers)
print('instr status', instr.status_code)
print('instr payload', instr.json()[:10])
admin_audits = client.get('/api/v1/audit/actions', headers=admin_headers)
print('admin status', admin_audits.status_code)
print('admin payload', admin_audits.json()[:10])

project = client.post(f"/api/v1/courses/{course.json()['id']}/projects", json={
    'project_name': 'Audit Project',
    'team_name': 'Audit Team',
    'description': 'Log project updates',
    'course_id': course.json()['id'],
    'member_ids': [],
    'jira_email': 'jira.owner@university.edu',
    'jira_domain': 'team.atlassian.net',
    'jira_project_key': 'JIRA',
    'jira_api_token': 'project-jira-token',
}, headers=instructor_headers)
print('project', project.status_code, project.json())
project_id = project.json()['id']

update_response = client.patch(f'/api/v1/projects/{project_id}', json={'project_name': 'Updated Audit Project'}, headers=instructor_headers)
print('update response', update_response.status_code, update_response.json())

delete_response = client.delete(f'/api/v1/projects/{project_id}', headers=instructor_headers)
print('delete response', delete_response.status_code, delete_response.json())

final_audits = client.get('/api/v1/audit/actions', headers=instructor_headers)
print('final audits len', len(final_audits.json()))
print('final actions', [item.get('action') for item in final_audits.json()])
