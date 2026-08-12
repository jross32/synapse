def landing_page() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trailmark</title>
<style>
body { font-family: Arial, sans-serif; background-color: #333; color: #fff; }
h1 { text-align: center; margin-top: 50px; }
button, input[type="email"], input[type="password"] { height: 44px; margin: 10px auto; display: block; width: 80%; }
</style>
</head>
<body>
<h1>Welcome to Trailmark</h1>
<p>Log your trails and share them with the world.</p>
<a href="/signup">Sign Up</a> | <a href="/login">Login</a>
</body>
</html>
"""

def signup_page() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trailmark - Sign Up</title>
<style>
body { font-family: Arial, sans-serif; background-color: #333; color: #fff; }
form { margin: 50px auto; width: 80%; text-align: center; }
button, input[type="email"], input[type="password"] { height: 44px; margin: 10px auto; display: block; width: 80%; }
</style>
</head>
<body>
<h1>Sign Up for Trailmark</h1>
<form id="signupForm">
    <input type="email" id="email" placeholder="Email" required>
    <input type="password" id="password" placeholder="Password" required>
    <button type="submit">Sign Up</button>
</form>
<div id="msg"></div>
<script>
document.getElementById('signupForm').addEventListener('submit', function(e) {
    e.preventDefault();
    fetch('/api/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: document.getElementById('email').value, password: document.getElementById('password').value })
    }).then(response => response.json())
      .then(data => {
          if (data.token) {
              localStorage.setItem('tm_token', data.token);
              window.location.href = '/dashboard';
          } else {
              document.getElementById('msg').innerText = data.error;
          }
      });
});
</script>
</body>
</html>
"""

def login_page() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trailmark - Login</title>
<style>
body { font-family: Arial, sans-serif; background-color: #333; color: #fff; }
form { margin: 50px auto; width: 80%; text-align: center; }
button, input[type="email"], input[type="password"] { height: 44px; margin: 10px auto; display: block; width: 80%; }
</style>
</head>
<body>
<h1>Login to Trailmark</h1>
<form id="loginForm">
    <input type="email" id="email" placeholder="Email" required>
    <input type="password" id="password" placeholder="Password" required>
    <button type="submit">Login</button>
</form>
<div id="msg"></div>
<script>
document.getElementById('loginForm').addEventListener('submit', function(e) {
    e.preventDefault();
    fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: document.getElementById('email').value, password: document.getElementById('password').value })
    }).then(response => response.json())
      .then(data => {
          if (data.token) {
              localStorage.setItem('tm_token', data.token);
              window.location.href = '/dashboard';
          } else {
              document.getElementById('msg').innerText = data.error;
          }
      });
});
</script>
</body>
</html>
"""

def dashboard_page() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trailmark - Dashboard</title>
<style>
body { font-family: Arial, sans-serif; background-color: #333; color: #fff; }
form { margin: 50px auto; width: 80%; text-align: center; }
button, input[type="text"], input[type="number"] { height: 44px; margin: 10px auto; display: block; width: 80%; }
#list { margin-top: 20px; }
</style>
</head>
<body>
<h1>Trailmark Dashboard</h1>
<form id="trailForm">
    <input type="text" id="name" placeholder="Trail Name" required>
    <input type="number" id="distance" placeholder="Distance (km)" required>
    <input type="date" id="date" required>
    <button type="submit">Add Trail</button>
</form>
<div id="list"></div>
<script>
function loadTrails() {
    const token = localStorage.getItem('tm_token');
    if (!token) {
        window.location.href = '/login';
    }
    fetch('/api/trails', {
        headers: { 'Authorization': `Bearer ${token}` }
    }).then(response => response.json())
      .then(data => {
          const list = document.getElementById('list');
          list.innerHTML = '';
          if (data.trails.length === 0) {
              list.innerText = 'No trails yet.';
          } else {
              data.trails.forEach(trail => {
                  const item = document.createElement('div');
                  item.innerHTML = `
                      <p>${trail.name} - ${trail.distance} km on ${trail.date}</p>
                      <button onclick="deleteTrail(${trail.id})">Delete</button>
                  `;
                  list.appendChild(item);
              });
          }
      });
}

function deleteTrail(id) {
    const token = localStorage.getItem('tm_token');
    fetch(`/api/trails/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
    }).then(loadTrails);
}

document.getElementById('trailForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const token = localStorage.getItem('tm_token');
    fetch('/api/trails', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
            name: document.getElementById('name').value,
            distance: parseFloat(document.getElementById('distance').value),
            date: document.getElementById('date').value
        })
    }).then(loadTrails);
});

loadTrails();
</script>
</body>
</html>
"""