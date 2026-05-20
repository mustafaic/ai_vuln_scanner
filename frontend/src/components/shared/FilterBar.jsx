/**
 * FilterBar — URL ve subdomain listelerinde kullanılan filtre çubuğu.
 *
 * Props:
 *  filters: object     — aktif filtre değerleri
 *  onChange: fn        — filtre değişince çağrılır ({ key, value })
 *  fields: FieldDef[]  — gösterilecek filtre alanları tanımı
 *
 * FieldDef: { key, label, type: 'text'|'select'|'number'|'checkbox', options? }
 */

export default function FilterBar({ filters = {}, onChange, fields = [] }) {
  if (!fields.length) return null;

  return (
    <div className="flex items-center gap-2 flex-wrap px-4 py-2 bg-[#111827] border-b border-[#374151]">
      {fields.map((field) => {
        const value = filters[field.key] ?? '';

        if (field.type === 'select') {
          return (
            <div key={field.key} className="flex items-center gap-1.5">
              {field.label && (
                <label className="text-[10px] text-gray-500">{field.label}</label>
              )}
              <select
                value={value}
                onChange={(e) => onChange({ key: field.key, value: e.target.value })}
                className="bg-[#1f2937] border border-[#374151] rounded text-xs text-gray-300 px-2 py-1 focus:outline-none focus:border-blue-500 min-w-[90px]"
              >
                <option value="">Tümü</option>
                {(field.options ?? []).map((opt) => (
                  <option key={opt.value ?? opt} value={opt.value ?? opt}>
                    {opt.label ?? opt}
                  </option>
                ))}
              </select>
            </div>
          );
        }

        if (field.type === 'number') {
          return (
            <div key={field.key} className="flex items-center gap-1.5">
              {field.label && (
                <label className="text-[10px] text-gray-500">{field.label}</label>
              )}
              <input
                type="number"
                value={value}
                min={field.min ?? 0}
                max={field.max ?? 100}
                placeholder={field.placeholder ?? '0'}
                onChange={(e) => onChange({ key: field.key, value: e.target.value })}
                className="bg-[#1f2937] border border-[#374151] rounded text-xs text-gray-300 px-2 py-1 w-16 focus:outline-none focus:border-blue-500"
              />
            </div>
          );
        }

        if (field.type === 'checkbox') {
          return (
            <label
              key={field.key}
              className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-400 hover:text-gray-200"
            >
              <input
                type="checkbox"
                checked={!!value}
                onChange={(e) => onChange({ key: field.key, value: e.target.checked })}
                className="accent-blue-500 w-3 h-3"
              />
              {field.label}
            </label>
          );
        }

        // default: text
        return (
          <div key={field.key} className="flex items-center gap-1.5">
            {field.label && (
              <label className="text-[10px] text-gray-500">{field.label}</label>
            )}
            <input
              type="text"
              value={value}
              placeholder={field.placeholder ?? field.label ?? ''}
              onChange={(e) => onChange({ key: field.key, value: e.target.value })}
              className="bg-[#1f2937] border border-[#374151] rounded text-xs text-gray-300 px-2 py-1 w-32 focus:outline-none focus:border-blue-500"
            />
          </div>
        );
      })}

      {/* Temizle butonu */}
      {Object.values(filters).some(Boolean) && (
        <button
          onClick={() => fields.forEach((f) => onChange({ key: f.key, value: '' }))}
          className="ml-auto text-[10px] text-gray-500 hover:text-gray-300 hover:underline"
        >
          Temizle ×
        </button>
      )}
    </div>
  );
}
