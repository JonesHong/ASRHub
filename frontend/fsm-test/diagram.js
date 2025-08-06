// 狀態圖視覺化
class StateDiagram {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.states = {};
        this.transitions = [];
        this.currentState = null;
    }
    
    // 定義狀態位置佈局
    getStatePositions(mode) {
        const layouts = {
            batch: {
                IDLE: { x: 150, y: 100 },
                PROCESSING: { x: 450, y: 100 },
                ERROR: { x: 300, y: 250 },
                RECOVERING: { x: 300, y: 350 }
            },
            'non-streaming': {
                IDLE: { x: 100, y: 100 },
                LISTENING: { x: 300, y: 100 },
                WAKE_WORD_DETECTED: { x: 500, y: 100 },
                RECORDING: { x: 500, y: 250 },
                TRANSCRIBING: { x: 300, y: 250 },
                ERROR: { x: 100, y: 350 },
                RECOVERING: { x: 300, y: 350 }
            },
            streaming: {
                IDLE: { x: 100, y: 100 },
                LISTENING: { x: 300, y: 100 },
                WAKE_WORD_DETECTED: { x: 500, y: 100 },
                STREAMING: { x: 500, y: 250 },
                ERROR: { x: 100, y: 350 },
                RECOVERING: { x: 300, y: 350 }
            }
        };
        
        return layouts[mode] || layouts.batch;
    }
    
    // 獲取狀態轉換定義
    getTransitions(mode) {
        const transitions = {
            batch: [
                { from: 'IDLE', to: 'PROCESSING', event: 'UPLOAD_FILE' },
                { from: 'PROCESSING', to: 'IDLE', event: 'TRANSCRIPTION_DONE' },
                { from: 'IDLE', to: 'ERROR', event: 'ERROR' },
                { from: 'PROCESSING', to: 'ERROR', event: 'ERROR' },
                { from: 'ERROR', to: 'RECOVERING', event: 'RECOVER' },
                { from: 'RECOVERING', to: 'IDLE', event: 'RESET' }
            ],
            'non-streaming': [
                { from: 'IDLE', to: 'LISTENING', event: 'START_LISTENING' },
                { from: 'LISTENING', to: 'WAKE_WORD_DETECTED', event: 'WAKE_WORD_TRIGGERED' },
                { from: 'WAKE_WORD_DETECTED', to: 'RECORDING', event: 'START_RECORDING' },
                { from: 'RECORDING', to: 'TRANSCRIBING', event: 'END_RECORDING' },
                { from: 'TRANSCRIBING', to: 'IDLE', event: 'TRANSCRIPTION_DONE' },
                { from: 'LISTENING', to: 'ERROR', event: 'ERROR' },
                { from: 'RECORDING', to: 'ERROR', event: 'ERROR' },
                { from: 'ERROR', to: 'RECOVERING', event: 'RECOVER' },
                { from: 'RECOVERING', to: 'IDLE', event: 'RESET' }
            ],
            streaming: [
                { from: 'IDLE', to: 'LISTENING', event: 'START_LISTENING' },
                { from: 'LISTENING', to: 'WAKE_WORD_DETECTED', event: 'WAKE_WORD_TRIGGERED' },
                { from: 'WAKE_WORD_DETECTED', to: 'STREAMING', event: 'START_STREAMING' },
                { from: 'STREAMING', to: 'IDLE', event: 'END_STREAMING' },
                { from: 'LISTENING', to: 'ERROR', event: 'ERROR' },
                { from: 'STREAMING', to: 'ERROR', event: 'ERROR' },
                { from: 'ERROR', to: 'RECOVERING', event: 'RECOVER' },
                { from: 'RECOVERING', to: 'IDLE', event: 'RESET' }
            ]
        };
        
        return transitions[mode] || transitions.batch;
    }
    
    // 渲染狀態圖
    render(mode, currentState) {
        this.currentState = currentState;
        const positions = this.getStatePositions(mode);
        const transitions = this.getTransitions(mode);
        
        // 創建 SVG
        const svg = this.createSVG();
        
        // 繪製轉換線
        transitions.forEach(transition => {
            this.drawTransition(svg, transition, positions);
        });
        
        // 繪製狀態節點
        Object.keys(positions).forEach(state => {
            this.drawState(svg, state, positions[state], state === currentState);
        });
        
        // 更新容器
        this.container.innerHTML = '';
        this.container.appendChild(svg);
    }
    
    createSVG() {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', '700');
        svg.setAttribute('height', '450');
        svg.setAttribute('viewBox', '0 0 700 450');
        
        // 添加箭頭標記定義
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        marker.setAttribute('id', 'arrow');
        marker.setAttribute('markerWidth', '10');
        marker.setAttribute('markerHeight', '10');
        marker.setAttribute('refX', '8');
        marker.setAttribute('refY', '3');
        marker.setAttribute('orient', 'auto');
        
        const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arrow.setAttribute('d', 'M0,0 L0,6 L9,3 z');
        arrow.setAttribute('fill', '#6c757d');
        
        marker.appendChild(arrow);
        defs.appendChild(marker);
        svg.appendChild(defs);
        
        return svg;
    }
    
    drawState(svg, stateName, position, isActive) {
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        
        // 繪製圓形
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', position.x);
        circle.setAttribute('cy', position.y);
        circle.setAttribute('r', '40');
        circle.setAttribute('fill', isActive ? '#4a90e2' : '#ffffff');
        circle.setAttribute('stroke', isActive ? '#357abd' : '#dee2e6');
        circle.setAttribute('stroke-width', isActive ? '3' : '2');
        
        // 添加動畫效果
        if (isActive) {
            const animate = document.createElementNS('http://www.w3.org/2000/svg', 'animate');
            animate.setAttribute('attributeName', 'r');
            animate.setAttribute('values', '40;45;40');
            animate.setAttribute('dur', '2s');
            animate.setAttribute('repeatCount', 'indefinite');
            circle.appendChild(animate);
        }
        
        // 繪製文字
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', position.x);
        text.setAttribute('y', position.y + 5);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', isActive ? 'white' : '#212529');
        text.setAttribute('font-size', '12');
        text.setAttribute('font-weight', isActive ? 'bold' : 'normal');
        text.textContent = stateName;
        
        group.appendChild(circle);
        group.appendChild(text);
        svg.appendChild(group);
    }
    
    drawTransition(svg, transition, positions) {
        const from = positions[transition.from];
        const to = positions[transition.to];
        
        if (!from || !to) return;
        
        // 計算線的起點和終點（考慮圓的半徑）
        const angle = Math.atan2(to.y - from.y, to.x - from.x);
        const startX = from.x + 40 * Math.cos(angle);
        const startY = from.y + 40 * Math.sin(angle);
        const endX = to.x - 40 * Math.cos(angle);
        const endY = to.y - 40 * Math.sin(angle);
        
        // 如果是自循環
        if (transition.from === transition.to) {
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            const d = `M ${from.x + 30} ${from.y - 30} Q ${from.x + 60} ${from.y} ${from.x + 30} ${from.y + 30}`;
            path.setAttribute('d', d);
            path.setAttribute('fill', 'none');
            path.setAttribute('stroke', '#6c757d');
            path.setAttribute('stroke-width', '2');
            path.setAttribute('marker-end', 'url(#arrow)');
            svg.appendChild(path);
        } else {
            // 繪製直線或曲線
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', startX);
            line.setAttribute('y1', startY);
            line.setAttribute('x2', endX);
            line.setAttribute('y2', endY);
            line.setAttribute('stroke', '#6c757d');
            line.setAttribute('stroke-width', '2');
            line.setAttribute('marker-end', 'url(#arrow)');
            svg.appendChild(line);
        }
        
        // 添加事件標籤
        const midX = (startX + endX) / 2;
        const midY = (startY + endY) / 2;
        
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', midX);
        text.setAttribute('y', midY - 5);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', '#6c757d');
        text.setAttribute('font-size', '10');
        text.setAttribute('font-style', 'italic');
        
        // 簡化事件名稱顯示
        const shortEventName = transition.event.replace(/_/g, ' ').toLowerCase();
        text.textContent = shortEventName;
        
        // 添加背景以提高可讀性
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', midX - 40);
        rect.setAttribute('y', midY - 15);
        rect.setAttribute('width', '80');
        rect.setAttribute('height', '15');
        rect.setAttribute('fill', 'white');
        rect.setAttribute('opacity', '0.9');
        
        svg.appendChild(rect);
        svg.appendChild(text);
    }
    
    // 高亮顯示路徑
    highlightPath(fromState, toState) {
        // 實現路徑高亮邏輯
        // 這可以在未來擴展以顯示動畫過渡
    }
}