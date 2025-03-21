// Add console logging for debugging
console.log("Dark mode script loaded");

document.addEventListener('DOMContentLoaded', function() {
  console.log("DOM content loaded");
  
  const themeToggle = document.getElementById('theme-toggle');
  const themeText = document.getElementById('theme-text');
  
  if (!themeToggle || !themeText) {
    console.error("Theme toggle elements not found:", { 
      themeToggleExists: !!themeToggle, 
      themeTextExists: !!themeText 
    });
    return;
  }
  
  console.log("Toggle elements found");
  
  // Check for saved theme preference or use user's system preference
  const savedTheme = localStorage.getItem('theme') || 
                    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  
  console.log("Saved theme:", savedTheme);
  
  // Apply initial theme
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateIcon(savedTheme);
  
  // Handle toggle click
  themeToggle.addEventListener('click', function(event) {
    console.log("Toggle clicked");
    event.preventDefault(); // Prevent link behavior
    
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    console.log("Switching from", currentTheme, "to", newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateIcon(newTheme);
  });
  
  function updateIcon(theme) {
    console.log("Updating icon for theme:", theme);
    if (theme === 'dark') {
      themeText.textContent = '☀️'; // Sun emoji for dark mode
    } else {
      themeText.textContent = '🌙'; // Moon emoji for light mode
    }
  }
}); 