(function () {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("document");
    const selectedFile = document.getElementById("selected-file");

    if (!dropZone || !fileInput || !selectedFile) {
        return;
    }

    function showSelectedFile(file) {
        selectedFile.textContent = file
            ? `Selected: ${file.name}`
            : "PDF, DOCX, TXT, JPG, JPEG, PNG, WEBP. Maximum size: 16 MB.";
    }

    ["dragenter", "dragover"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.add("is-dragging");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.remove("is-dragging");
        });
    });

    dropZone.addEventListener("drop", (event) => {
        const file = event.dataTransfer.files[0];
        if (!file) {
            return;
        }

        fileInput.files = event.dataTransfer.files;
        showSelectedFile(file);
    });

    fileInput.addEventListener("change", () => {
        showSelectedFile(fileInput.files[0]);
    });
})();
