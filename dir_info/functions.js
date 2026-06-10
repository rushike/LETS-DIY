async function loadLs() {
  const path = document.getElementById('dirInput').value.trim();
  const errorMsg = document.getElementById('errorMsg');
  errorMsg.textContent = '';
  document.getElementById('dirTableBody').innerHTML = '';
  flatData = [];

  if (!path) {
    errorMsg.textContent = 'Please enter a directory path.';
    return;
  }

  try {
    const response = await fetch(`http://localhost:8000/ls?dirpath=${encodeURIComponent(path)}`);
    if (!response.ok) {
      const errData = await response.json();
      errorMsg.textContent = errData.detail || 'Failed to list directory.';
      return;
    }

    const data = await response.json();

    // Convert /ls response into flatData format
    flatData = data.map(item => {
      const id = Math.random().toString(36).substr(2, 9);
      return {
        id,
        parentId: null,
        name: item.name,
        size: item.size ?? 0,
        type: item.total_items === 0 ? 'File' : 'Folder', // crude check
        depth: 0,
        childrenHidden: true
      };
    });

    buildTable();
  } catch (e) {
    errorMsg.textContent = 'Error fetching data.';
    console.error(e);
  }
}
