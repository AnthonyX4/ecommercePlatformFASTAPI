import "../css/Home.css"
import {useState, useEffect} from "react"
import "../components/NavBar.jsx"
import NavBar from "../components/NavBar.jsx"
import { Link } from "react-router-dom"
import ItemCard from "../components/ItemCard.jsx"

function Home() {
    
    const [sneakers, setSneakers] = useState([]) // will be used for the feed
    const [loading, setLoading] = useState(true) // prolly won't need this for our case, but it's good to handle it anyway
    const username = "demo-user-1" // change this
    // ** write the useEffect to load the shoes here
    
    useEffect(() => {
        fetch("http://localhost:8000/api/products") // the port in which our api is running
        .then((data) => data.json()) 
        .then((data) => { // this is needed because .json() also returns a promise (async things)
            const sneakers_data = data.products // the api returns one page: {products, total, skip, limit, has_more}
            setSneakers(sneakers_data)
            setLoading(false) // no longer loading, because the data arrived and has been stored properly.
        })
    }, [])

    if (loading) return <p>Loading your feed, stand by... 😭🫡</p>
    
    return (
        <>
            <div className="home-content">
                <div className="home-nav">
                    <NavBar username={username}/>
                </div>
                <div className="home-grid">
                    {/* need a loop here to print out the grid of sneaker cards */}
                    {sneakers && sneakers.map(
                        (sneaker) => {
                            return <ItemCard sneaker={sneaker} key={sneaker.id}></ItemCard>
                        }
                    )}
                </div>
            </div>
        </>
    )

}

export default Home