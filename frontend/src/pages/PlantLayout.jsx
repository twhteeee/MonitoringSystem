import React, { useState, useEffect } from 'react';
import { Settings, Battery, Droplets, Zap } from 'lucide-react';
import { format } from 'date-fns';

const MachineCard = ({ name, type, running, power, runtime, level }) => {
  const isRunning = running;
  const statusColor = isRunning ? 'var(--accent-secondary)' : 'var(--text-secondary)';
  const statusBg = isRunning ? 'rgba(16, 185, 129, 0.1)' : 'rgba(148, 163, 184, 0.1)';

  return (
    <div className="glass-card" style={{ padding: '1rem', borderTop: `4px solid ${statusColor}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
        <div>
          <h4 style={{ fontWeight: 600, fontSize: '1.1rem' }}>{name}</h4>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{type}</span>
        </div>
        <div style={{ 
          background: statusBg, 
          color: statusColor, 
          padding: '0.25rem 0.5rem', 
          borderRadius: '1rem', 
          fontSize: '0.75rem',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: '0.25rem'
        }}>
          {isRunning ? <span style={{width: 8, height: 8, borderRadius: '50%', background: statusColor, display: 'inline-block'}}></span> : null}
          {isRunning ? 'RUNNING' : 'STOPPED'}
        </div>
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
        {power !== undefined && (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}><Zap size={12} className="inline mr-1" /> Power</span>
            <span style={{ fontWeight: 600 }}>{power} kW</span>
          </div>
        )}
        
        {runtime !== undefined && (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}><Settings size={12} className="inline mr-1" /> Runtime</span>
            <span style={{ fontWeight: 600 }}>{runtime} h</span>
          </div>
        )}
        
        {level !== undefined && (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}><Droplets size={12} className="inline mr-1" /> Level</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ flex: 1, background: 'rgba(255,255,255,0.1)', height: '6px', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{ background: 'var(--accent-primary)', height: '100%', width: `${level}%` }}></div>
              </div>
              <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{level}%</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default function PlantLayout() {
  const [selectedTime, setSelectedTime] = useState(format(new Date(), "yyyy-MM-dd'T'HH:mm"));
  const [loading, setLoading] = useState(false);
  const [machines, setMachines] = useState([]);

  const fetchMachines = () => {
    setLoading(true);
    setTimeout(() => {
      setMachines([
        { id: 1, name: 'Molino 1', type: 'Ball Mill', running: true, power: 124.5, runtime: 4520 },
        { id: 2, name: 'Molino 2', type: 'Ball Mill', running: false, power: 0, runtime: 3100 },
        { id: 3, name: 'Molino 3', type: 'Ball Mill', running: true, power: 196.9, runtime: 8900 },
        { id: 4, name: 'Secadero 1', type: 'Dryer', running: true, power: 45.2, runtime: 1200 },
        { id: 5, name: 'Silo A', type: 'Storage', running: false, level: 78 },
        { id: 6, name: 'Silo B', type: 'Storage', running: false, level: 34 },
        { id: 7, name: 'Vat Tank 1', type: 'Tank', running: true, power: 5.2, level: 92, runtime: 5600 },
        { id: 8, name: 'Vat Tank 2', type: 'Tank', running: false, power: 0, level: 12, runtime: 4200 },
      ]);
      setLoading(false);
    }, 500);
  };

  useEffect(() => {
    fetchMachines();
  }, []);

  const handleUpdate = () => {
    fetchMachines();
  };

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">Plant Layout & Runtime Snapshot</h2>
      </div>

      <div className="glass-card mb-6" style={{ marginBottom: '1.5rem' }}>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Select a specific date and time to view the plant's exact state, accumulated runtime, and energy consumption.
        </p>
        <div className="controls-row">
          <div className="input-group">
            <label className="input-label">Snapshot Date & Time</label>
            <input 
              type="datetime-local" 
              className="input-field" 
              value={selectedTime}
              onChange={(e) => setSelectedTime(e.target.value)}
            />
          </div>
          <div className="input-group">
            <button className="btn" onClick={handleUpdate}>
              Fetch Snapshot
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="glass-card" style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          Loading snapshot...
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1.5rem' }}>
          {machines.map(machine => (
            <MachineCard key={machine.id} {...machine} />
          ))}
        </div>
      )}
    </div>
  );
}
