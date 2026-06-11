
// Tema claro/oscuro
function setTheme(theme) {
  const themeLink = document.getElementById('themeLink');
  const themeToggle = document.getElementById('themeToggle');
  if (themeLink) {
    themeLink.href = `https://bootswatch.com/5/${theme}/bootstrap.min.css`;
    localStorage.setItem('theme', theme);
    if (themeToggle) {
      themeToggle.textContent = theme === 'flatly' ? 'Tema oscuro' : 'Tema claro';
    }
  }
}

function toggleTheme() {
  const currentTheme = localStorage.getItem('theme') || 'flatly';
  const newTheme = currentTheme === 'flatly' ? 'darkly' : 'flatly';
  setTheme(newTheme);
}

function loadTheme() {
  const savedTheme = localStorage.getItem('theme') || 'flatly';
  setTheme(savedTheme);
}

document.addEventListener('DOMContentLoaded', loadTheme);

const btnDelete= document.querySelectorAll('.btn-borrar');
if(btnDelete) {
  const btnArray = Array.from(btnDelete);
  btnArray.forEach((btn) => {
    btn.addEventListener('click', (e) => {
      if(!confirm('¿Está seguro de querer borrar?')){
        e.preventDefault();
      }
    });
  })
}
