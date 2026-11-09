const tg = window.Telegram.WebApp;
tg.expand(); // Открываем на весь экран

// Восстанавливаем счет из кэша (LocalStorage)
let score = localStorage.getItem('tma_score') ? parseInt(localStorage.getItem('tma_score')) : 0;
const scoreElement = document.getElementById('score');
const btn = document.getElementById('click-btn');

scoreElement.innerText = score;

btn.addEventListener('click', (e) => {
    // Вибрация (Haptic Feedback)
    if (tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('medium');
    }

    score++;
    scoreElement.innerText = score;
    localStorage.setItem('tma_score', score);

    // Анимация вылетающих цифр
    const floatText = document.createElement('div');
    floatText.innerText = '+1';
    floatText.style.position = 'absolute';
    
    // Делаем появление чуть выше кнопки, если e.clientX пустой (при мультитаче)
    const x = e.clientX || window.innerWidth / 2;
    const y = e.clientY || window.innerHeight / 2;
    
    floatText.style.left = (x - 10) + 'px';
    floatText.style.top = (y - 20) + 'px';
    floatText.style.color = '#00f3ff';
    floatText.style.fontWeight = 'bold';
    floatText.style.fontSize = '1.5rem';
    floatText.style.pointerEvents = 'none';
    floatText.style.animation = 'floatUp 0.8s ease-out forwards';
    
    document.body.appendChild(floatText);
    setTimeout(() => floatText.remove(), 800);
});

// Стили для анимации +1
const style = document.createElement('style');
style.innerHTML = `
@keyframes floatUp {
    0% { transform: translateY(0); opacity: 1; }
    100% { transform: translateY(-80px); opacity: 0; }
}`;
document.head.appendChild(style);
