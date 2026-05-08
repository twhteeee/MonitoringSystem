import React, { useState, useEffect } from 'react';

const TreeCard = ({ title, value, type = 'child', childrenNodes = [] }) => {
  return (
    <div className="tree-node">
      <div className={`tree-card ${type}`}>
        <div style={{ fontSize: '0.85rem', opacity: 0.9 }}>{title}</div>
        <div className="value-text">{value} kW</div>
      </div>
      {childrenNodes.length > 0 && (
        <>
          <div className="tree-line-v"></div>
          <div className="tree-children" style={{
            position: 'relative',
            marginTop: '1.5rem',
            display: 'flex',
            gap: '2rem'
          }}>
            {/* Draw horizontal line connecting children */}
            {childrenNodes.length > 1 && (
              <div style={{
                position: 'absolute',
                top: 0,
                left: 'calc(50% / ' + childrenNodes.length + ')',
                right: 'calc(50% / ' + childrenNodes.length + ')',
                height: '2px',
                background: 'var(--border-color)',
                zIndex: 0
              }}></div>
            )}
            
            {childrenNodes.map((child, index) => (
              <div key={index} style={{ position: 'relative', paddingTop: '1.5rem' }}>
                <div style={{
                  position: 'absolute',
                  top: 0,
                  left: '50%',
                  width: '2px',
                  height: '1.5rem',
                  background: 'var(--border-color)',
                  transform: 'translateX(-50%)',
                  zIndex: 0
                }}></div>
                <TreeCard {...child} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export default function PowerTree() {
  const [data, setData] = useState(null);

  useEffect(() => {
    // Simulate fetching data from backend
    setTimeout(() => {
      setData({
        title: "Total electricidad",
        value: "708.00",
        type: "root",
        childrenNodes: [
          {
            title: "Cuadro general (1C)",
            value: "51.00",
            childrenNodes: [
              { title: "Secadero 1", value: "0.08", type: "leaf" },
              { title: "Molino 1", value: "0.32", type: "leaf" },
              { title: "Molino 2", value: "0.00", type: "leaf" }
            ]
          },
          {
            title: "Total electricidad Planta Sur",
            value: "672.00",
            childrenNodes: [
              {
                title: "Cuadro general (2C)",
                value: "246.00",
                childrenNodes: [
                  { title: "Molino 3", value: "196.90", type: "leaf" },
                  { title: "Molino 4", value: "0.80", type: "leaf" },
                  { title: "Molino 5", value: "1.20", type: "leaf" }
                ]
              },
              {
                title: "Cuadro general (3C)",
                value: "426.40",
                childrenNodes: [
                  { title: "Molino 8", value: "0.00", type: "leaf" },
                  { title: "Molino 9", value: "420.00", type: "leaf" }
                ]
              }
            ]
          }
        ]
      });
    }, 500);
  }, []);

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">Power Distribution Tree</h2>
        <div className="flex gap-2">
          <button className="btn btn-secondary" style={{ marginRight: '0.5rem' }}>Electricidad</button>
          <button className="btn btn-secondary" style={{ marginRight: '0.5rem', opacity: 0.5 }}>Gas</button>
          <button className="btn btn-secondary" style={{ opacity: 0.5 }}>Aire comprimido</button>
        </div>
      </div>
      
      <div className="glass-card" style={{ minHeight: '600px', display: 'flex', justifyContent: 'center', paddingTop: '2rem', overflowX: 'auto' }}>
        {data ? (
          <TreeCard {...data} />
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            Loading power data...
          </div>
        )}
      </div>
    </div>
  );
}
