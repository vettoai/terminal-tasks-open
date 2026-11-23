export default function Home() {
  return <main><h1>Campaign administration</h1>{['camp_ops_demo', 'camp_diamond', 'camp_large'].map(id =>
    <p key={id}><a href={`/campaigns/${id}`}>{id}</a></p>)}</main>;
}
