import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { format, subHours } from 'date-fns';

export default function Dashboard() {
  const [data, setData] = useState([]);
  const [machine, setMachine] = useState('Molino 1');
  const [startDate, setStartDate] = useState(format(subHours(new Date(), 24), "yyyy-MM-dd'T'HH:mm"));
  const [endDate, setEndDate] = useState(format(new Date(), "yyyy-MM-dd'T'HH:mm"));
  const [loading, setLoading] = useState(false);

  // Generate mock data for the chart
  const generateMockData = () => {
    const mock = [];
    const now = new Date(endDate).getTime();
    const start = new Date(startDate).getTime();
    const step = (now - start) / 24; // 24 points
    
    for (let i = 0; i <= 24; i++) {
      const time = new Date(start + step * i);
      mock.push({
        time: format(time, 'yyyy-MM-dd HH:mm'),
        consumo: Math.random() > 0.8 ? 0 : 60 + Math.random() * 20, // simulate some zero periods
        velocidad: Math.random() > 0.8 ? 0 : 800 + Math.random() * 50,
      });
    }
    return mock;
  };

  useEffect(() => {
    setLoading(true);
    // Simulate API fetch to /api/v1/signals/{machine_id}/raw
    setTimeout(() => {
      setData(generateMockData());
      setLoading(false);
    }, 600);
  }, [machine, startDate, endDate]);

  const handleApply = () => {
    setLoading(true);
    setTimeout(() => {
      setData(generateMockData());
      setLoading(false);
    }, 600);
  };

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">Historical Data Analysis</h2>
      </div>

      <div className="glass-card mb-6" style={{ marginBottom: '1.5rem' }}>
        <div className="controls-row">
          <div className="input-group">
            <label className="input-label">Equipment</label>
            <select 
              className="input-field" 
              value={machine} 
              onChange={(e) => setMachine(e.target.value)}
            >
              <option value="Molino 1">Molino 1</option>
              <option value="Molino 2">Molino 2</option>
              <option value="Molino 3">Molino 3</option>
              <option value="Secadero 1">Secadero 1</option>
            </select>
          </div>
          
          <div className="input-group">
            <label className="input-label">Start Date & Time</label>
            <input 
              type="datetime-local" 
              className="input-field" 
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          
          <div className="input-group">
            <label className="input-label">End Date & Time</label>
            <input 
              type="datetime-local" 
              className="input-field" 
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>

          <div className="input-group">
            <button className="btn" onClick={handleApply}>
              Apply Filter
            </button>
          </div>
        </div>
      </div>

      <div className="glass-card">
        <h3 style={{ marginBottom: '1.5rem', fontWeight: 600 }}>{machine} - Power & Speed over time</h3>
        {loading ? (
          <div style={{ height: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            Loading data...
          </div>
        ) : (
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={data}
                margin={{ top: 5, right: 30, left: 20, bottom: 65 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                <XAxis 
                  dataKey="time" 
                  stroke="#94a3b8" 
                  angle={-90} 
                  textAnchor="end" 
                  height={80} 
                  tick={{ fontSize: 12 }}
                />
                <YAxis yAxisId="left" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <YAxis yAxisId="right" orientation="right" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                  itemStyle={{ color: '#f8fafc' }}
                />
                <Legend verticalAlign="bottom" height={36} />
                <Line 
                  yAxisId="left" 
                  type="stepAfter" 
                  dataKey="consumo" 
                  name="Consumo Molino (A)" 
                  stroke="#8b5cf6" 
                  strokeWidth={2} 
                  dot={false}
                  activeDot={{ r: 6 }} 
                />
                <Line 
                  yAxisId="right" 
                  type="monotone" 
                  dataKey="velocidad" 
                  name="Velocidad (kg/h)" 
                  stroke="#10b981" 
                  strokeWidth={2} 
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
