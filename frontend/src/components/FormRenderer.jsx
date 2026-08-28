import { useState } from 'react'

export default function FormRenderer({ form, values, onChange }) {
  const set = (key, v) => onChange({ ...values, [key]: v })
  return (
    <div className="form-render">
      {form.fields.map((f) => {
        const key = `field_${f.id}`
        const type = f.field_type?.code_name
        return (
          <div key={f.id} className="fr-field">
            {type === 'header' ? (
              <h3 className="fr-header">{f.name}</h3>
            ) : (
              <label>
                <span className="fr-label">{f.name}{f.is_required && ' *'}</span>
                {(type === 'input') && (
                  <input value={values[key] || ''} required={f.is_required}
                         onChange={(e) => set(key, e.target.value)} />
                )}
                {type === 'number' && (
                  <input type="number" value={values[key] || ''} required={f.is_required}
                         onChange={(e) => set(key, e.target.value)} />
                )}
                {type === 'date' && (
                  <input type="date" value={values[key] || ''} required={f.is_required}
                         onChange={(e) => set(key, e.target.value)} />
                )}
                {type === 'long_text' && (
                  <textarea rows={3} value={values[key] || ''} required={f.is_required}
                            onChange={(e) => set(key, e.target.value)} />
                )}
                {type === 'poll' && (
                  <div className="choice-group">
                    {f.options.map((o) => (
                      <label key={o.id} className="choice">
                        <input type="radio" name={key} checked={values[key] === o.name}
                               onChange={() => set(key, o.name)} /> {o.name}
                      </label>
                    ))}
                  </div>
                )}
                {type === 'multi_poll' && (
                  <div className="choice-group">
                    {f.options.map((o) => (
                      <label key={o.id} className="choice">
                        <input type="checkbox"
                               checked={(values[key] || []).includes(o.name)}
                               onChange={(e) => {
                                 const cur = values[key] || []
                                 set(key, e.target.checked ? [...cur, o.name]
                                                          : cur.filter((x) => x !== o.name))
                               }} /> {o.name}
                      </label>
                    ))}
                  </div>
                )}
                {type === 'spinner' && (
                  <select value={values[key] || ''} required={f.is_required}
                          onChange={(e) => set(key, e.target.value)}>
                    <option value="">—</option>
                    {f.options.map((o) => <option key={o.id} value={o.name}>{o.name}</option>)}
                  </select>
                )}
                {type === 'file' && (
                  <input type="file" required={f.is_required}
                         onChange={(e) => set(key, e.target.files?.[0]?.name || 'uploaded')} />
                )}
              </label>
            )}
          </div>
        )
      })}
    </div>
  )
}
