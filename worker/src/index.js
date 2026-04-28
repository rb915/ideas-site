export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    try {
      const { page_id, action } = await request.json();

      if (!page_id) {
        return json({ error: 'page_id required' }, 400);
      }

      // Default action is archive (dismiss). Also support "restore".
      const archived = action === 'restore' ? false : true;

      const res = await fetch(`https://api.notion.com/v1/pages/${page_id}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${env.NOTION_API_KEY}`,
          'Notion-Version': '2022-06-28',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ archived }),
      });

      const data = await res.json();

      if (!res.ok) {
        return json({ error: data.message || 'Notion API error' }, res.status);
      }

      return json({ success: true, archived });
    } catch (err) {
      return json({ error: err.message }, 500);
    }
  },
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
    },
  });
}
