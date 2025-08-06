// Zen 版本的狀態圖視覺化 - 更緊湊的佈局
class StateDiagramZen {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentState = null;
    }
    
    // 緊湊的狀態位置佈局
    getStatePositions(mode) {
        const layouts = {
            batch: {
                IDLE: { x: 100, y: 60 },
                PROCESSING: { x: 250, y: 60 },
                ERROR: { x: 175, y: 140 },
                RECOVERING: { x: 175, y: 200 }
            },
            'non-streaming': {
                IDLE: { x: 60, y: 60 },
                LISTENING: { x: 180, y: 60 },
                WAKE_WORD_DETECTED: { x: 300, y: 60 },
                RECORDING: { x: 300, y: 140 },
                TRANSCRIBING: { x: 180, y: 140 },
                ERROR: { x: 60, y: 200 },
                RECOVERING: { x: 180, y: 200 }
            },
            streaming: {
                IDLE: { x: 60, y: 60 },
                LISTENING: { x: 180, y: 60 },
                WAKE_WORD_DETECTED: { x: 300, y: 60 },
                STREAMING: { x: 300, y: 140 },
                ERROR: { x: 60, y: 200 },
                RECOVERING: { x: 180, y: 200 }
            }
        };
        
        return layouts[mode] || layouts.batch;
    }
    
    // 獲取狀態轉換定義
    getTransitions(mode) {
        const transitions = {
            batch: [
                { from: 'IDLE', to: 'PROCESSING', event: 'UPLOAD' },
                { from: 'PROCESSING', to: 'IDLE', event: 'DONE' },
                { from: 'IDLE', to: 'ERROR', event: 'ERROR' },
                { from: 'PROCESSING', to: 'ERROR', event: 'ERROR' },
                { from: 'ERROR', to: 'RECOVERING', event: 'RECOVER' },
                { from: 'RECOVERING', to: 'IDLE', event: 'RESET' }
            ],
            'non-streaming': [
                { from: 'IDLE', to: 'LISTENING', event: 'START' },
                { from: 'LISTENING', to: 'WAKE_WORD_DETECTED', event: 'WAKE' },
                { from: 'WAKE_WORD_DETECTED', to: 'RECORDING', event: 'REC' },
                { from: 'RECORDING', to: 'TRANSCRIBING', event: 'END' },
                { from: 'TRANSCRIBING', to: 'IDLE', event: 'DONE' },
                { from: 'LISTENING', to: 'ERROR', event: 'ERR' },
                { from: 'RECORDING', to: 'ERROR', event: 'ERR' },
                { from: 'ERROR', to: 'RECOVERING', event: 'RCV' },
                { from: 'RECOVERING', to: 'IDLE', event: 'RST' }
            ],
            streaming: [
                { from: 'IDLE', to: 'LISTENING', event: 'START' },
                { from: 'LISTENING', to: 'WAKE_WORD_DETECTED', event: 'WAKE' },
                { from: 'WAKE_WORD_DETECTED', to: 'STREAMING', event: 'STREAM' },
                { from: 'STREAMING', to: 'IDLE', event: 'END' },
                { from: 'LISTENING', to: 'ERROR', event: 'ERR' },
                { from: 'STREAMING', to: 'ERROR', event: 'ERR' },
                { from: 'ERROR', to: 'RECOVERING', event: 'RCV' },
                { from: 'RECOVERING', to: 'IDLE', event: 'RST' }
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
        svg.setAttribute('width', '360');
        svg.setAttribute('height', '260');
        svg.setAttribute('viewBox', '0 0 360 260');
        
        // 添加箭頭標記定義
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        marker.setAttribute('id', 'arrow');
        marker.setAttribute('markerWidth', '8');
        marker.setAttribute('markerHeight', '8');
        marker.setAttribute('refX', '6');
        marker.setAttribute('refY', '3');
        marker.setAttribute('orient', 'auto');
        
        const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arrow.setAttribute('d', 'M0,0 L0,6 L6,3 z');
        arrow.setAttribute('fill', '#999');
        
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
        circle.setAttribute('r', '25');
        
        // 根據狀態設置顏色
        const stateColors = {
            'IDLE': '#6c757d',
            'LISTENING': '#20c997',
            'WAKE_WORD_DETECTED': '#ffc107',
            'RECORDING': '#dc3545',
            'STREAMING': '#007bff',
            'TRANSCRIBING': '#6f42c1',
            'PROCESSING': '#28a745',
            'ERROR': '#ff3333',
            'RECOVERING': '#fd7e14'
        };
        
        if (isActive) {
            circle.setAttribute('fill', stateColors[stateName] || '#4a90e2');
            circle.setAttribute('stroke', stateColors[stateName] || '#4a90e2');
            circle.setAttribute('stroke-width', '3');
            circle.setAttribute('fill-opacity', '1');
            
            // 添加脈動動畫
            const animate = document.createElementNS('http://www.w3.org/2000/svg', 'animate');
            animate.setAttribute('attributeName', 'r');
            animate.setAttribute('values', '25;28;25');
            animate.setAttribute('dur', '2s');
            animate.setAttribute('repeatCount', 'indefinite');
            circle.appendChild(animate);
        } else {
            circle.setAttribute('fill', '#fff');
            circle.setAttribute('stroke', '#ddd');
            circle.setAttribute('stroke-width', '1');
        }
        
        // 繪製文字 - 簡短版本
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', position.x);
        text.setAttribute('y', position.y + 4);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', isActive ? 'white' : '#666');
        text.setAttribute('font-size', '10');
        text.setAttribute('font-weight', isActive ? 'bold' : 'normal');
        
        // 使用縮寫
        const shortNames = {
            'IDLE': 'IDLE',
            'LISTENING': 'LISTEN',
            'WAKE_WORD_DETECTED': 'WAKE',
            'RECORDING': 'REC',
            'STREAMING': 'STREAM',
            'TRANSCRIBING': 'TRANS',
            'PROCESSING': 'PROC',
            'ERROR': 'ERROR',
            'RECOVERING': 'RECOV'
        };
        
        text.textContent = shortNames[stateName] || stateName;
        
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
        const startX = from.x + 25 * Math.cos(angle);
        const startY = from.y + 25 * Math.sin(angle);
        const endX = to.x - 25 * Math.cos(angle);
        const endY = to.y - 25 * Math.sin(angle);
        
        // 繪製線
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', startX);
        line.setAttribute('y1', startY);
        line.setAttribute('x2', endX);
        line.setAttribute('y2', endY);
        line.setAttribute('stroke', '#ccc');
        line.setAttribute('stroke-width', '1');
        line.setAttribute('marker-end', 'url(#arrow)');
        svg.appendChild(line);
        
        // 添加事件標籤（極簡）
        const midX = (startX + endX) / 2;
        const midY = (startY + endY) / 2;
        
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', midX);
        text.setAttribute('y', midY - 3);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', '#999');
        text.setAttribute('font-size', '8');
        text.textContent = transition.event;
        
        // 添加白色背景
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        const bbox = { width: transition.event.length * 5, height: 10 };
        rect.setAttribute('x', midX - bbox.width / 2);
        rect.setAttribute('y', midY - 8);
        rect.setAttribute('width', bbox.width);
        rect.setAttribute('height', bbox.height);
        rect.setAttribute('fill', 'white');
        rect.setAttribute('opacity', '0.9');
        
        svg.appendChild(rect);
        svg.appendChild(text);
    }
}